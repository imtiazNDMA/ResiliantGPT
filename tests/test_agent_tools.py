
import unittest
from unittest.mock import MagicMock
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.search_tool import SearchTool
from tools.image_tool import ImageTool
from services.vector_store import VectorStore
from services.llm_service import LLMService

class TestAgentTools(unittest.TestCase):
    def setUp(self):
        # Mock dependencies to test tool logic in isolation
        self.mock_vector_store = MagicMock(spec=VectorStore)
        self.mock_llm_service = MagicMock(spec=LLMService)
        
        self.search_tool = SearchTool(vector_store=self.mock_vector_store)
        self.image_tool = ImageTool(llm_service=self.mock_llm_service)

    def test_search_tool_schema(self):
        """Verify SearchTool follows OpenAI function schema"""
        schema = self.search_tool.to_function_schema()
        print(f"\n[SearchTool Schema]: {schema}")
        self.assertEqual(schema["function"]["name"], "search_documents")
        self.assertTrue("query" in schema["function"]["parameters"]["properties"])

    def test_search_tool_execution_success(self):
        """Verify SearchTool formats results correctly"""
        # Setup mock return
        self.mock_vector_store.search_documents.return_value = (
            ["Content of doc 1"], 
            [{"document_id": "test.pdf", "page": 1}]
        )
        
        result = self.search_tool.run(query="test query")
        print(f"\n[Search Result]: {result}")
        
        self.assertIn("Source 1 (test.pdf)", result)
        self.assertIn("Content of doc 1", result)

    def test_search_tool_no_results(self):
        """Verify SearchTool handles empty results"""
        self.mock_vector_store.search_documents.return_value = ([], [])
        result = self.search_tool.run(query="empty")
        self.assertEqual(result, "No relevant documents found in the knowledge base.")

    def test_image_tool_schema(self):
        """Verify ImageTool follows OpenAI function schema"""
        schema = self.image_tool.to_function_schema()
        print(f"\n[ImageTool Schema]: {schema}")
        self.assertEqual(schema["function"]["name"], "generate_image")
        self.assertTrue("prompt" in schema["function"]["parameters"]["properties"])

    def test_image_tool_execution_simulated(self):
        """Verify ImageTool handles generation logic"""
        # Mock the entire execution flow to avoid loading Stable Diffusion
        # We need to mock the image object returned by call_stable_diffusion
        mock_image = MagicMock()
        # Mock save method
        def side_effect(buf, format):
            buf.write(b"fake_image_bytes")
        mock_image.save.side_effect = side_effect
        
        self.mock_llm_service.call_stable_diffusion.return_value = mock_image
        
        result = self.image_tool.run(prompt="a cat")
        print(f"\n[Image Result]: {result}")
        
        self.assertTrue(result.startswith("IMAGE_GENERATED:"))

if __name__ == '__main__':
    unittest.main()
