import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.llm_service import LLMService
from utils.response_formatter import ResponseClassifier

print("Testing LLM response generation with context...")
try:
    llm = LLMService()
    # Simple test with context
    result = llm.extract_result(
        text=["This is a test document about disaster management."],
        query="What is disaster management?",
        recent_history=[],
        references_for_each_chunk=[],
    )
    print("LLM test with context PASSED. Response length:", len(result))
    print("Response preview:", result[:200])
except Exception as e:
    print(f"LLM test with context FAILED: {e}")
    import traceback

    traceback.print_exc()

print("\nTesting LLM response generation without context...")
try:
    llm = LLMService()
    # Test without context (empty vector store)
    result = llm.extract_result(
        text=[],
        query="What is disaster management?",
        recent_history=[],
        references_for_each_chunk=[],
    )
    print("LLM test without context PASSED. Response length:", len(result))
    print("Response preview:", result[:200])
except Exception as e:
    print(f"LLM test without context FAILED: {e}")
    import traceback

    traceback.print_exc()

print("\nTesting ResponseClassifier...")
try:
    classifier = ResponseClassifier()
    from langchain_ollama import ChatOllama

    llm_client = ChatOllama(
        model="llama3.1", temperature=0.3, base_url="http://localhost:11434"
    )

    # Test classification
    response_type, critical_info, response_structure = classifier.classify_and_extract(
        query="What is disaster management?",
        context="This is a test document about disaster management.",
        llm_client=llm_client,
    )
    print("Classification test PASSED.")
    print("Response type:", response_type)
    print("Response structure:", response_structure)
except Exception as e:
    print(f"Classification test FAILED: {e}")
    import traceback

    traceback.print_exc()
