import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config

try:
    from controllers import newfunc
    from services.vector_store import VectorStore
    from services.llm_service import LLMService

    print("Imports successful.")
except ImportError as e:
    print(f"Import Failed: {e}")
    exit(1)

print("Checking VectorStore Init...")
try:
    vs = VectorStore(mode="pakistan")
    print(f"VectorStore Init Passed: {vs.collection.name}")
except Exception as e:
    print(f"VectorStore Init Failed: {e}")

print("Checking LLMService Init...")
try:
    llm = LLMService()
    print("LLMService Init Passed.")
except Exception as e:
    print(f"LLMService Init Failed: {e}")

print("Phase 2 Smoke Test Passed.")
