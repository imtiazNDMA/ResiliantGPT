import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config
from services import database
import shutil

print(f"Secret Key loaded: {Config.SECRET_KEY != 'default-dev-key-do-not-use-in-prod'}")
# Note: config.py has a default value, so this might prompt false negative if user didn't make .env
# But we just want to ensure it runs.

print("Testing Database...")
try:
    if os.path.exists(Config.DATABASE_PATH):
        try:
            os.remove(Config.DATABASE_PATH)
        except:
            print("Could not remove existing db, using it.")

    database.init_db()

    conv_id = "test_123"
    data = {
        "title": "Test Chat",
        "history": [{"user": "hello", "bot": "hi"}],
        "mode": "pakistan",
    }

    database.save_conversation(conv_id, data)
    retrieved = database.get_conversation(conv_id)

    assert retrieved["title"] == "Test Chat"
    assert len(retrieved["history"]) == 1

    print("Database verification PASSED.")

except Exception as e:
    print(f"Database verification FAILED: {e}")

# Clean up
if os.path.exists(Config.DATABASE_PATH):
    try:
        os.remove(Config.DATABASE_PATH)
        print("Cleaned up test db.")
    except:
        pass
