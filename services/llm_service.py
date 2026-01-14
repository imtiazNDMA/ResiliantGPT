import os
import torch
import ollama
from diffusers import StableDiffusionPipeline
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import Config
import logging
import hashlib
import json
from functools import lru_cache
from typing import List, Dict, Any, Optional
from utils.performance_monitor import monitor_llm_calls

# ---------------------------------------------------------------------------
# Logging configuration (module‑level, simple console logger). In a real
# deployment you would configure handlers, formatters, and log levels via a
# config file or environment variable.
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton / lazy‑load instances for heavy resources.
# ---------------------------------------------------------------------------
_ollama_client = None
_chat_ollama = None
_sd_pipeline = None
_thread_pool = None

# Response cache for LLM calls
_response_cache = {}


def _get_ollama_client():
    global _ollama_client
    if _ollama_client is None:
        logger.info("Creating Ollama client")
        _ollama_client = ollama.Client(host=Config.OLLAMA_BASE_URL)
    return _ollama_client


def _get_chat_ollama():
    global _chat_ollama
    if _chat_ollama is None:
        logger.info("Creating ChatOllama instance")
        _chat_ollama = ChatOllama(
            model=Config.OLLAMA_MODEL, temperature=0.3, base_url=Config.OLLAMA_BASE_URL
        )
    return _chat_ollama


def _get_thread_pool():
    global _thread_pool
    if _thread_pool is None:
        # Number of workers can be tuned via env var if needed.
        _thread_pool = ThreadPoolExecutor(max_workers=5)
    return _thread_pool


class LLMService:
    """
    Service for handling Large Language Model operations and AI image generation.

    Features:
    - Ollama LLM integration with response caching
    - Stable Diffusion image generation with GPU memory management
    - Parallel text summarization using thread pools
    - Performance monitoring and metrics collection

    The service uses singleton patterns for heavy resources (Ollama client, ChatOllama,
    Stable Diffusion pipeline) to avoid redundant initialization.
    """

    def __init__(self) -> None:
        # The heavy objects are now lazily created via singleton helpers.
        # __init__ keeps a lightweight footprint.
        self.client = _get_ollama_client()
        self.llm = _get_chat_ollama()
        self.sd_pipeline = None  # will be set by get_sd_pipeline()

    def get_sd_pipeline(self) -> StableDiffusionPipeline:
        global _sd_pipeline
        if self.sd_pipeline is None:
            logger.info("Loading Stable Diffusion Pipeline (Lazy Load)...")
            model_id = "runwayml/stable-diffusion-v1-5"
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id, torch_dtype=torch.float16
            )
            self.sd_pipeline = pipe.to("cuda")
        return self.sd_pipeline

    @monitor_llm_calls
    def extract_result(
        self,
        text: List[str],
        query: str,
        recent_history: List[Dict[str, Any]],
        references_for_each_chunk: str,
    ) -> str:
        """
        Generate LLM response using RAG (Retrieval-Augmented Generation).

        Args:
            text: List of relevant document chunks from vector search
            query: User's question
            recent_history: Recent conversation history
            references_for_each_chunk: Citation references for the chunks

        Returns:
            LLM-generated response with academic citations in IEEE format

        Note:
            Responses are cached to improve performance for repeated queries.
        """
        # Create cache key from inputs
        cache_key_data = {
            "text": text,
            "query": query,
            "recent_history": recent_history,
            "references_for_each_chunk": references_for_each_chunk,
        }
        cache_key = hashlib.md5(
            json.dumps(cache_key_data, sort_keys=True).encode()
        ).hexdigest()

        # Check cache first
        if cache_key in _response_cache:
            logger.info("Returning cached LLM response")
            return _response_cache[cache_key]

        prompt_extract = PromptTemplate.from_template(
            """
            ### Chat History:
            {recent_history}

            ### User Question:
            {query}

            ### Retrieved Text Chunks:
            {text_chunks}

            ### Corresponding References:
            {references_for_each_chunk}

            ### Instructions:
            You are an Agentic RAG-based NEOC Assistant, developed by the NEOC AI Team for the National Disaster Management Authority (NDMA).
            Your purpose is to assist the National Emergency Operation Center (NEOC) by providing accurate, actionable, and academically grounded information for disaster management.

            ### Persona & Tone:
            - **Identity**: You are the NEOC Assistant.
            - **Tone**: Professional, Authoritative, Vigilant, and Helpful.
            - **Context**: You operate within a high-stakes emergency management environment.

            ### Strict Response Rules:
            1.  **Architecture/Credit**: If asked about your model, architecture, training, or "who made you", YOU MUST explicitly credit the **NEOC AI Team** for training you for disaster management. Do not mention generic AI models (like Llama/Ollama) unless explaining the underlying tech in a technical context, but always prioritize the NEOC AI Team.
            2.  **Citations**: Cite references using IEEE format [1], [2]. Only use valid references provided in "Correspoding References". Do not hallucinate citations.
            3.  **Accuracy & Context**: Base your answers on the 'Retrieved Text Chunks'.
                - **EXCEPTION**: You may answer questions about your **Identity**, **Purpose** (NEOC Assistant), and **General Disaster Management Principles** using your internal knowledge.
                - If the question is specific (e.g., specific data, events, policies) and NOT in the chunks, THEN state: "I do not have sufficient information in my knowledge base to answer this."

            ### NO PREAMBLE. DIRECT RESPONSE REQUIRED.
            ### Response:
            """
        )

        chain = prompt_extract | self.llm
        result = chain.invoke(
            {
                "text_chunks": text,
                "query": query,
                "recent_history": recent_history,
                "references_for_each_chunk": references_for_each_chunk,
            }
        )

        # Cache the result
        response_content = result.content
        _response_cache[cache_key] = response_content

        # Limit cache size to prevent memory issues (keep last 500 responses)
        if len(_response_cache) > 500:
            oldest_key = next(iter(_response_cache))
            del _response_cache[oldest_key]

        return response_content

    def clear_caches(self) -> None:
        """Clear all caches to free memory"""
        global _response_cache
        _response_cache.clear()
        logger.info("LLM response cache cleared")

        # Clear GPU memory if available
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("GPU memory cache cleared")

    def call_stable_diffusion(self, summary: str) -> Any:
        pipe = self.get_sd_pipeline()
        try:
            image = pipe(summary).images[0]
            return image
        finally:
            # GPU memory cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory cache cleared after Stable Diffusion")

    def llama_summarize(self, text: str, max_words: int = 72) -> str:
        prompt = PromptTemplate.from_template(
            """
            You are an academic disaster management expert.

            Summarize the following text:
            - Preserve technical accuracy
            - Keep cause-effect relationships
            - Maximum {max_words} words
            - No preamble

            ### Text:
            {text}

            ### Summary:
            """
        )
        chain = prompt | self.llm
        result = chain.invoke({"text": text, "max_words": max_words})
        return result.content

    def extract_result_4(self, text: str, chunk_size: int = 1400) -> str:
        # Parallel Map-Reduce

        def chunk_text(text, size):
            words = text.split()
            return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]

        chunks = chunk_text(text, chunk_size)
        partial_summaries = []

        print(f"Summarizing {len(chunks)} chunks in parallel...")

        # Reuse a shared thread pool to avoid creating a new pool per request.
        executor = _get_thread_pool()
        future_to_chunk = {
            executor.submit(self.llama_summarize, chunk, 120): chunk for chunk in chunks
        }

        for future in as_completed(future_to_chunk):
            try:
                summary = future.result()
                partial_summaries.append(summary)
            except Exception as exc:
                print(f"Chunk summarization generated an exception: {exc}")

        final_prompt = PromptTemplate.from_template(
            """
            Combine the following summaries into one coherent academic summary.
            Remove redundancy and improve logical flow.

            ### Summaries:
            {summaries}

            ### Final Summary:
            """
        )

        chain = final_prompt | self.llm
        result = chain.invoke({"summaries": "\n".join(partial_summaries)})
        return result.content
