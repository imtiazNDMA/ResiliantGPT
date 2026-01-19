import os
import io
from uuid import uuid4
from config import Config
from services.llm_service import LLMService
from services.vector_store import VectorStore
from werkzeug.datastructures import FileStorage
from services.speech_service import transcribe
from typing import Optional, Union, List, Any, Dict


def newfunc(
    user_text: str,
    action: str,
    mode: str,
    chat_history: List[Dict[str, Any]],
    files: Optional[List[FileStorage]] = None,
    path: Optional[str] = None,
    vector_store: Optional[VectorStore] = None,
) -> Union[str, bytes]:
    """
    Main controller function handling different types of requests.

    Args:
        user_text: Input text from user
        action: Type of action ('search', 'insert', 'audio', 'image')
        mode: Conversation mode ('general' or 'pakistan')
        chat_history: List of previous conversation messages
        files: Optional list of uploaded files for 'insert' action
        path: Optional path parameter for audio processing
        vector_store: Optional pre-initialized VectorStore instance

    Returns:
        Response based on action type:
        - 'search': LLM generated response string
        - 'insert': Success message string
        - 'audio': Transcribed text string
        - 'image': Base64 encoded image bytes

    Raises:
        ValueError: If no VectorStore available for the specified mode
    """

    text = ""
    start_time = os.times()

    if vector_store is None:
        from app import vector_store_instances

        vector_store = vector_store_instances.get(
            mode, vector_store_instances.get("general")
        )
        if vector_store is None:
            raise ValueError(f"No VectorStore available for mode: {mode}")

    if action == "insert":
        if not files:
            return "No files provided"
        print("Files in insert: ", files)
        vector_store.insert_docs(files)
        return "Documents processed successfully."

    elif action == "search":
        print("User Text: ", user_text)
        context, ref = vector_store.search_documents(user_text)
        text = vector_store.call_llm(context, user_text, chat_history, ref)
        return text

    elif action == "audio":
        filename = f"audio_{uuid4()}.wav"
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)

        with open(filepath, "wb") as f:
            f.write(user_text)

        user_message = transcribe(filepath)
        return user_message

    elif action == "image":
        summary = LLMService().llama_summarize(text=user_text)
        print("Summary for image: ", summary)
        image = LLMService().call_stable_diffusion(summary)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        image_base64 = base64.b64encode(buf.read()).decode("utf-8")

        return image_base64

    else:
        return text
