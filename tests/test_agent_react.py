
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from controllers import AgentController
from services.vector_store import VectorStore
from services.llm_service import LLMService

class TestAgentReact(unittest.TestCase):
    def setUp(self):
        self.mock_vector_store = MagicMock(spec=VectorStore)
        with patch('controllers.LLMService') as MockLLM:
            self.agent = AgentController(mode="general", vector_store=self.mock_vector_store)
            self.mock_llm_service = MockLLM.return_value

    def test_multi_step_reasoning(self):
        """Test a scenario where agent searches then draws"""
        # Step 1: LLM decides to search
        output_1 = "Thought: I need to find flood protocols first.\nAction: search_documents\nAction Input: flood protocols"
        # Step 2: LLM processes observation and decides to draw
        output_2 = "Thought: I have the info. Now I will generate a diagram.\nAction: generate_image\nAction Input: evacuation diagram"
        # Step 3: LLM gives final answer
        output_3 = "Final Answer: Here are the protocols and the diagram."

        self.mock_llm_service.llama_summarize.side_effect = [output_1, output_2, output_3]
        self.mock_vector_store.search_documents.return_value = (["Flood info"], [{"source": "test.pdf"}])
        
        # Mock image tool separately since it's instantiated in AgentController
        self.agent.tools["generate_image"].run = MagicMock(return_value="IMAGE_GENERATED:123")
        
        result = self.agent.execute_loop("Find flood info and draw it", [])
        
        self.assertEqual(result, "Here are the protocols and the diagram.")
        self.assertEqual(self.mock_llm_service.llama_summarize.call_count, 3)
        self.mock_vector_store.search_documents.assert_called_once()
        self.agent.tools["generate_image"].run.assert_called_once()

    def test_direct_final_answer(self):
        """Test agent giving final answer immediately"""
        self.mock_llm_service.llama_summarize.return_value = "Final Answer: I am ResilienceGPT."
        result = self.agent.execute_loop("Who are you?", [])
        self.assertEqual(result, "I am ResilienceGPT.")
        self.mock_vector_store.search_documents.assert_not_called()

if __name__ == '__main__':
    unittest.main()
