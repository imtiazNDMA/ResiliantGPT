import chromadb
from services.llm_service import LLMService
from sentence_transformers import SentenceTransformer
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
import PyPDF2
from utils import text_processing
from docx import Document
import pandas as pd
import io
from tqdm import tqdm
from config import Config
import hashlib
from functools import lru_cache
from typing import List, Dict, Any, Tuple, Optional
from werkzeug.datastructures import FileStorage
from utils.performance_monitor import monitor_embedding_calls, time_function

# Two blank lines required before a top‑level class definition per PEP8


class VectorStore:
    """
    Vector store implementation backed by ChromaDB with optimized embeddings.

    Features:
    - Lazy-loaded SentenceTransformer model shared across instances
    - LRU caching for embeddings to avoid recomputation
    - Batch processing for improved performance
    - Support for multiple document formats (PDF, TXT, DOCX, CSV, XLS, XLSX)

    Attributes:
        mode: Conversation mode ('general' or 'pakistan') affecting document filtering
        collection: ChromaDB collection for vector storage
        _embedding_model: Shared SentenceTransformer instance
        _embedding_cache: LRU cache for computed embeddings
    """

    # Singleton for the embedding model – shared across all VectorStore instances.
    _embedding_model = None

    # LRU cache for embeddings to avoid recomputing identical texts
    _embedding_cache = {}

    @staticmethod
    @lru_cache(maxsize=1000)
    def _cached_encode(text: str) -> Tuple[float, ...]:
        """Cache embeddings by text hash to avoid recomputation"""
        if VectorStore._embedding_model is None:
            raise RuntimeError("Embedding model not initialized")

        # Create hash of text for cache key
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

        # Check memory cache first
        if text_hash in VectorStore._embedding_cache:
            return tuple(VectorStore._embedding_cache[text_hash])

        # Compute embedding
        embedding = VectorStore._embedding_model.encode(text).tolist()

        # Store in memory cache
        VectorStore._embedding_cache[text_hash] = embedding

        return tuple(embedding)

    @staticmethod
    @monitor_embedding_calls
    def _batch_encode(texts: List[str]) -> List[List[float]]:
        """Batch encode multiple texts for better performance"""
        if VectorStore._embedding_model is None:
            raise RuntimeError("Embedding model not initialized")

        # Check cache for each text
        uncached_texts = []
        uncached_indices = []
        cached_embeddings = [None] * len(texts)

        for i, text in enumerate(texts):
            text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            if text_hash in VectorStore._embedding_cache:
                cached_embeddings[i] = VectorStore._embedding_cache[text_hash]
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Batch encode uncached texts
        if uncached_texts:
            batch_embeddings = VectorStore._embedding_model.encode(
                uncached_texts
            ).tolist()

            # Store in cache and result
            for i, (text, embedding) in enumerate(
                zip(uncached_texts, batch_embeddings)
            ):
                text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
                VectorStore._embedding_cache[text_hash] = embedding
                cached_embeddings[uncached_indices[i]] = embedding

        return cached_embeddings

    def __init__(self, mode: str) -> None:
        self.logger = logging.getLogger(__name__)
        # Split long line for readability
        self.chroma_client = chromadb.PersistentClient(path=Config.CHROMA_DB_PATH)
        self.mode = mode  # store mode for later use

        # Use a single collection and store the mode as metadata on each document.
        # This avoids proliferation of collections and simplifies queries.
        self.collection_name = "disaster_papers"
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )
        self.logger.info(
            "Initialized VectorStore (mode=%s, collection=%s)",
            mode,
            self.collection_name,
        )

        # Lazy‑load the embedding model.
        if VectorStore._embedding_model is None:
            self.logger.info("Loading SentenceTransformer model for embeddings")
            VectorStore._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.embedding_model = VectorStore._embedding_model

    def extract_references_from_text(self, full_text: str) -> str:
        """Return the substring starting at the first occurrence of a
        references heading (case‑insensitive)."""
        import re
        # Pattern to find headings like "References", "Bibliography", "Works Cited"
        # It looks for the keyword on its own line or with minimal surrounding characters
        pattern = r"(?i)(\n\s*(?:references|bibliography|works cited)[\s:-]*\n)"
        match = re.search(pattern, full_text)
        
        if match:
            return full_text[match.start():]
        return ""

    def read_pdf(self, file: FileStorage) -> Tuple[str, str]:
        """Extract raw text and reference section from a PDF file."""
        reader = PyPDF2.PdfReader(file)
        # Memory optimisation: use StringIO instead of a list of strings
        text_buffer = io.StringIO()

        for page in reader.pages:
            text_buffer.write(page.extract_text())
            text_buffer.write(" ")

        whole_text = text_buffer.getvalue()
        text_buffer.close()

        ref_lines = self.extract_references_from_text(whole_text)
        return whole_text, ref_lines

    def read_txt(self, file: FileStorage) -> Tuple[str, str]:
        file.seek(0)
        raw_data = file.read()

        for encoding in ["utf-8", "latin-1", "windows-1252"]:
            try:
                full_text = raw_data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Unable to decode text file.")

        references = self.extract_references_from_text(full_text)
        return full_text, references

    def read_docx(self, file: FileStorage) -> Tuple[str, str]:
        doc = Document(file)
        full_text = "\n".join([para.text for para in doc.paragraphs])
        references = self.extract_references_from_text(full_text)
        return full_text, references

    def convert_to_csv(self, file: FileStorage) -> Tuple[str, str]:
        filename = file.filename
        ext = filename.rsplit(".", 1)[1].lower()

        if ext == "csv":
            file.seek(0)
            df = pd.read_csv(file)
        elif ext in ["xls", "xlsx"]:
            df = pd.read_excel(file)
        else:
            raise ValueError("Unsupported spreadsheet format")

        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        return csv_buffer.getvalue(), []

    def process_and_insert_file(self, file: FileStorage) -> None:
        """Read *file*, chunk it, embed the chunks and store them in Chroma.

        The function works for PDF, TXT, DOCX and CSV/Excel files.
        """
        # Generator/Stream based processing
        ext = file.filename.rsplit(".", 1)[1].lower()
        output, references = "", ""

        if ext == "pdf":
            output, references = self.read_pdf(file)
        elif ext == "txt":
            output, references = self.read_txt(file)
        elif ext == "docx":
            output, references = self.read_docx(file)
        elif ext in ["csv", "xls", "xlsx"]:
            output, references = self.convert_to_csv(file)
        else:
            self.logger.info("Skipping unsupported file: %s", file.filename)
            return

        # Create chunks immediately and free raw text memory if possible
        chunks = self.create_insert_chunks(output)

        # Process references – helper expects lists of chunks and references.
        processed_chunks_with_refs = text_processing.get_references(
            [chunks], [references]
        )

        self.logger.info(
            "Inserting %d chunks for %s",
            len(processed_chunks_with_refs),
            file.filename,
        )

        # Batch collect ids, texts, embeddings and metadata for a single add call.
        ids = []
        texts = []
        embeddings = []
        metadatas = []

        # Extract texts for batch processing
        chunk_texts = [doc["text"] for doc in processed_chunks_with_refs]

        # Batch encode all texts at once for better performance
        batch_embeddings = VectorStore._batch_encode(chunk_texts)

        for doc, embedding in tqdm(
            zip(processed_chunks_with_refs, batch_embeddings),
            desc=f"Processing {file.filename}",
            total=len(processed_chunks_with_refs),
        ):
            # Attach mode metadata so we can filter later if needed.
            doc["metadata"]["mode"] = self.mode
            # Keep references as a list/dict, not a string.
            doc["metadata"]["cited_references"] = {
                "references": doc["metadata"].get("cited_references", [])
            }

            ids.append(doc["id"])
            texts.append(doc["text"])
            embeddings.append(embedding)
            metadatas.append(doc["metadata"])

        if ids:
            self.collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )

    def insert_docs(self, files: List[FileStorage]) -> None:
        """
        Process and insert multiple documents into the vector store.

        Args:
            files: List of uploaded file objects to process and store

        Supported formats: PDF, TXT, DOCX, CSV, XLS, XLSX
        Each file is chunked, embedded, and stored with metadata.
        """
        # Now accepts files argument directly instead of self.files
        for file in files:
            try:
                self.process_and_insert_file(file)
            except Exception as e:
                print(f"Error processing {file.filename}: {e}")

        print("Documents stored successfully.")

    def create_insert_chunks(self, text: str) -> List[str]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=600, chunk_overlap=100, separators=["\n\n", "\n", "."]
        )
        return splitter.split_text(text)

    def search_documents(self, query: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Search for documents similar to the query using vector similarity.

        Args:
            query: Search query string

        Returns:
            Tuple of (documents, metadata) where:
            - documents: List of relevant document chunks
            - metadata: List of metadata dictionaries for each chunk
        """
        query_embedding = list(VectorStore._cached_encode(query))
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=10
        )
        self.retrieved_docs = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        full_context = results["documents"][0] if results["documents"] else []
        self.context = full_context
        return self.context, metadatas

    def call_llm(
        self,
        context1: List[str],
        query: str,
        recent_history: List[Dict[str, Any]],
        ref: List[Dict[str, Any]],
    ) -> str:
        # Extract and format references for the LLM service
        formatted_references = self._format_references_for_llm(ref)

        extract_result = LLMService().extract_result(
            text=context1,
            query=query,
            recent_history=recent_history,
            references_for_each_chunk=formatted_references,
        )
        return extract_result

    def _format_references_for_llm(
        self, metadatas: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format metadata references for the LLM service with validation"""
        formatted_refs = []

        for metadata in metadatas:
            cited_refs = metadata.get("cited_references", [])
            for ref in cited_refs:
                # Validate that the reference has actual content
                citation_id = ref.get("citation_id", "").strip()
                title = ref.get("title", "").strip()
                authors = ref.get("authors", "").strip()
                raw_reference = ref.get("raw_reference", "").strip()

                # Only include references that have meaningful content
                # Must have citation_id OR (title/authors AND raw_reference)
                has_citation_id = bool(citation_id)
                has_meaningful_content = bool(title or authors) and bool(
                    raw_reference and len(raw_reference) > 10
                )

                if has_citation_id or has_meaningful_content:
                    formatted_refs.append(
                        {
                            "citation_id": citation_id,
                            "title": title,
                            "authors": authors,
                            "year": ref.get("year", "").strip(),
                            "raw_reference": raw_reference,
                        }
                    )

        # Remove duplicates based on citation_id if present, otherwise based on content
        seen = set()
        unique_refs = []
        for ref in formatted_refs:
            # Create a unique identifier for deduplication
            if ref["citation_id"]:
                identifier = ref["citation_id"]
            else:
                identifier = f"{ref['title']}_{ref['authors']}_{ref['year']}"

            if identifier not in seen:
                seen.add(identifier)
                unique_refs.append(ref)

        return unique_refs
