import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.llm_service import LLMService


def test_fix():
    service = LLMService()

    print("\n--- Test: Identity Check (Should NOT have disclaimer) ---")
    query = "Who are you?"
    response = service.extract_result(
        text="",  # No context provided
        query=query,
        recent_history=[],
        references_for_each_chunk="",
    )
    print(f"Q: {query}")
    print(f"A: {response}")


if __name__ == "__main__":
    test_fix()
