import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.llm_service import LLMService


def test_persona():
    service = LLMService()

    # Test 1: Credit Rule
    print("\n--- Test 1: Credit Rule ---")
    query_credit = "Who developed you and what is your model?"
    response_credit = service.extract_result(
        text="", query=query_credit, recent_history=[], references_for_each_chunk=""
    )
    print(f"Q: {query_credit}")
    print(f"A: {response_credit}")

    # Test 2: Disaster Context
    print("\n--- Test 2: Disaster Context ---")
    query_disaster = "How should we respond to a flood warning?"
    # Mock context
    context = "Floods require immediate evacuation to higher ground. Do not walk through moving water. [Reference: NDMA Guidelines 2024]"
    response_disaster = service.extract_result(
        text=context,
        query=query_disaster,
        recent_history=[],
        references_for_each_chunk="[1] NDMA Guidelines 2024",
    )
    print(f"Q: {query_disaster}")
    print(f"A: {response_disaster}")

    # Test 3: Irrelevant Question
    print("\n--- Test 3: Irrelevant Question ---")
    query_joke = "Tell me a funny joke about cats."
    response_joke = service.extract_result(
        text="", query=query_joke, recent_history=[], references_for_each_chunk=""
    )
    print(f"Q: {query_joke}")
    print(f"A: {response_joke}")


if __name__ == "__main__":
    test_persona()
