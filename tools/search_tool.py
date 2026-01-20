from typing import List, Dict, Any, Type
from pydantic import BaseModel, Field
from tools.base import BaseTool
from services.vector_store import VectorStore

class SearchArgs(BaseModel):
    query: str = Field(description="The question or topic to search for in the knowledge base.")

class SearchTool(BaseTool):
    """
    Tool for searching the internal document knowledge base.
    Use this to find specific information, facts, or context from uploaded files.
    """
    name: str = "search_documents"
    description: str = "Search the knowledge base for relevant documents and information."
    args_schema: Type[BaseModel] = SearchArgs

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def run(self, query: str) -> str:
        """
        Executes the search and returns a formatted string of results.
        """
        try:
            # Re-use the existing logic from vector_store
            # Search documents returns (documents, metadata)
            chunks, metadatas = self.vector_store.search_documents(query)
            
            if not chunks:
                return "No relevant documents found in the knowledge base."

            # Format results for the Agent to "read"
            results = []
            for i, (chunk, meta) in enumerate(zip(chunks, metadatas)):
                source = meta.get("document_id", "Unknown Doc")
                results.append(f"Source {i+1} ({source}):\n{chunk}\n")
            
            return "\n".join(results)
            
        except Exception as e:
            return f"Error executing search: {str(e)}"
