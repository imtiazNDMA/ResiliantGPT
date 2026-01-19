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
from typing import List, Dict, Any, Optional, Tuple
from utils.performance_monitor import monitor_llm_calls
from utils.response_formatter import (
    ResponseClassifier,
    ResponseFormatter,
    ResponseType,
    CriticalInformation,
)

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
        references_for_each_chunk: List[Dict[str, Any]],
    ) -> str:
        """
        Generate intelligent LLM response using RAG with response classification and formatting.

        Args:
            text: List of relevant document chunks from vector search
            query: User's question
            recent_history: Recent conversation history
            references_for_each_chunk: Citation references for the chunks

        Returns:
            Professionally formatted response with critical information extraction

        Note:
            Uses intelligent response classification and structured formatting for better user experience.
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

        # Step 1: Classify response type and extract critical information
        context_text = " ".join(text)
        classifier = ResponseClassifier()
        response_type, critical_info, response_structure = (
            classifier.classify_and_extract(query, context_text, self.llm)
        )

        # Step 2: Generate base response using enhanced prompt
        base_response = self._generate_base_response(
            text,
            query,
            recent_history,
            references_for_each_chunk,
            response_type,
            critical_info,
        )

        # Step 3: Format the final response professionally
        formatter = ResponseFormatter()
        formatted_response = formatter.format_response(
            response_type, critical_info, base_response, references_for_each_chunk
        )

        # Cache the result
        _response_cache[cache_key] = formatted_response

        # Limit cache size to prevent memory issues (keep last 500 responses)
        if len(_response_cache) > 500:
            oldest_key = next(iter(_response_cache))
            del _response_cache[oldest_key]

        return formatted_response

    def _generate_base_response(
        self,
        text: List[str],
        query: str,
        recent_history: List[Dict[str, Any]],
        references_for_each_chunk: List[Dict[str, Any]],
        response_type: ResponseType,
        critical_info: CriticalInformation,
    ) -> str:
        """Generate the base response content using type-specific prompting"""

        # Create type-specific prompt instructions
        type_instructions = self._get_type_specific_instructions(
            response_type, critical_info
        )

        prompt_extract = PromptTemplate.from_template(
            f"""
            ### Chat History:
            {{recent_history}}

            ### User Question:
            {{query}}

            ### Retrieved Context:
            {{text_chunks}}

            ### Instructions:
            You are ResilienceGPT, a helpful and professional AI assistant for the National Disaster Management Authority (NDMA).
            Your goal is to provide clear, accurate, and conversationally natural responses based on the provided context.

            ### Guidelines:
            1.  **Be Natural**: Speak like a human expert. Avoid robotic headers like "Response:" or "Answer:".
            2.  **Use Context**: Base your answer primarily on the 'Retrieved Context'.
            3.  **Be Helpful**: If the context doesn't fully answer the question, politely state what is available.
            4.  **Citations**: Naturally integrate citations if relevant, but do not force them.
            5.  **Neat Formatting**: Use paragraphs, bullet points, and bold text to make the answer easy to read.

            ### Tone:
            Professional, Helpful, and Natural.

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

        return result.content

    def _get_type_specific_instructions(
        self, response_type: ResponseType, critical_info: CriticalInformation
    ) -> str:
        """Get response type-specific instructions for the LLM"""

        base_instructions = """
        Provide a comprehensive, professional response that directly addresses the user's question.
        Focus on being helpful, accurate, and actionable while maintaining an authoritative tone.
        """

        type_specific = {
            ResponseType.FACTUAL: """
            Provide factual information with clear definitions and explanations.
            Include relevant historical context and current status where applicable.
            """,
            ResponseType.PROCEDURAL: """
            Provide step-by-step procedures and protocols.
            Include checklists, timelines, and specific actions to be taken.
            Emphasize safety and compliance requirements.
            """,
            ResponseType.CONCEPTUAL: """
            Explain conceptual frameworks, theories, and principles.
            Provide context for how concepts interrelate and apply in practice.
            Include examples and real-world applications.
            """,
            ResponseType.ANALYTICAL: """
            Provide analytical assessment including risk evaluation and impact analysis.
            Include data-driven insights and comparative analysis where relevant.
            Highlight key findings and implications.
            """,
            ResponseType.ACTIONABLE: """
            Focus on immediate, actionable steps and recommendations.
            Prioritize urgent actions and emergency response protocols.
            Include clear timelines and responsible parties.
            """,
            ResponseType.TECHNICAL: """
            Provide technical details including specifications, formulas, and calculations.
            Include technical standards and requirements.
            Explain technical concepts clearly for both technical and non-technical audiences.
            """,
            ResponseType.REGULATORY: """
            Focus on legal and regulatory requirements, policies, and compliance.
            Include specific laws, regulations, and policy frameworks.
            Highlight compliance obligations and consequences of non-compliance.
            """,
            ResponseType.EDUCATIONAL: """
            Provide educational content focused on training and capacity building.
            Include learning objectives, key concepts, and practical applications.
            Structure content for effective knowledge transfer.
            """,
            ResponseType.PREDICTIVE: """
            Provide predictive analysis including scenarios, trends, and projections.
            Include risk projections and mitigation strategies.
            Focus on future implications and preparedness measures.
            """,
        }

        return base_instructions + type_specific.get(response_type, "")

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
