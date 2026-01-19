import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import conversations

print("Testing conversations function...")
try:
    conv_id, image_base64, bot_response = conversations(
        conv_id=None,
        user_message="Hello, what is disaster management?",
        mode="general",
        type="normal",
        generate_image=False,
    )
    print("Conversations test PASSED.")
    print("Conversation ID:", conv_id)
    print("Bot response length:", len(bot_response))
    print("Response preview:", bot_response[:200])
except Exception as e:
    print(f"Conversations test FAILED: {e}")
    import traceback

    traceback.print_exc()
