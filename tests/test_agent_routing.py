
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from controllers import AgentController
from services.vector_store import VectorStore
from services.llm_service import LLMService

class TestAgentRouting(unittest.TestCase):
    def setUp(self):
        self.mock_vector_store = MagicMock(spec=VectorStore)
        # We need to mock LLMService because it's instantiated inside AgentController
        with patch('controllers.LLMService') as MockLLM:
            self.agent = AgentController(mode="general", vector_store=self.mock_vector_store)
            self.mock_llm_service = MockLLM.return_value

    def test_route_to_search(self):
        """Test if 'search_documents' is selected for a factual question"""
        self.mock_llm_service.llama_summarize.return_value = "search_documents"
        self.mock_vector_store.search_documents.return_value = (["Context"], [{"id": 1}])
        self.mock_vector_store.call_llm.return_value = "Final Answer"
        
        result = self.agent.route_and_execute("How do I handle floods?", [])
        
        self.assertEqual(result, "Final Answer")
        self.mock_llm_service.llama_summarize.assert_called()
        self.mock_vector_store.search_documents.assert_called_once()

    def test_route_to_image(self):
        """Test if 'generate_image' is selected for a visual request"""
        self.mock_llm_service.llama_summarize.return_value = "generate_image"
        
        # Mock the image tool run method directly since it was already tested
        self.agent.tools["generate_image"].run = MagicMock(return_value="IMAGE_GENERATED:base64data")
        
        result = self.agent.route_and_execute("Draw a cat", [])
        
        self.assertEqual(result, "IMAGE_GENERATED:base64data")
        self.agent.tools["generate_image"].run.assert_called_once_with("Draw a cat")

    def test_route_to_chat(self):
        """Test if 'chat' is selected for a simple greeting"""
        self.mock_llm_service.llama_summarize.return_value = "chat"
        self.mock_vector_store.call_llm.return_value = "Hello!"
        
        result = self.agent.route_and_execute("Hi there", [])
        
        self.assertEqual(result, "Hello!")
        # Search should NOT be called
        self.mock_vector_store.search_documents.assert_not_called()

if __name__ == '__main__':
    unittest.main()
