from typing import Type
from pydantic import BaseModel, Field
from tools.base import BaseTool
from services.llm_service import LLMService

class ImageArgs(BaseModel):
    prompt: str = Field(description="A detailed visual description of the image to look for or generate.")

class ImageTool(BaseTool):
    """
    Tool for generating images based on a text prompt.
    Use this when the user explicitly asks to 'generate an image', 'show me', or 'draw'.
    """
    name: str = "generate_image"
    description: str = "Generate an image from a text description using Stable Diffusion."
    args_schema: Type[BaseModel] = ImageArgs

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def run(self, prompt: str) -> str:
        """
        Generates an image and returns a base64 string or status.
        For the agent loop, returning the Base64 string might be too large.
        Ideally, we return a success message and side-load the image into the conversation/UI context.
        But for now, let's return a special token or the base64 if it's small enough? 
        The prompt says 'generate relevant imagery'.
        Let's perform the generation and return a placeholder that the Frontend knows how to render.
        """
        try:
            # In the current controller flow, image generation returns a base64 string.
            # We can reuse that logic.
            
            # Note: The original controller logic 'summarized' the text first. 
            # The agent should be smart enough to pass a good prompt.
            
            image = self.llm_service.call_stable_diffusion(prompt)
            
            import io
            import base64
            
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)
            image_base64 = base64.b64encode(buf.read()).decode("utf-8")
            
            # We return a specially formatted string that the UI/Loop can detect as an image
            return f"IMAGE_GENERATED:{image_base64}"
            
        except Exception as e:
            return f"Error generating image: {str(e)}"
