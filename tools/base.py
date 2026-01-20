from abc import ABC, abstractmethod
from typing import Any, Dict, Type
from pydantic import BaseModel

class BaseTool(ABC):
    """
    Abstract base class for all Agent tools.
    Encapsulates a specific capability (e.g., search, image generation)
    in a way that can be described to and invoked by an LLM.
    """
    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Execute the tool with the provided arguments.
        """
        pass

    def to_function_schema(self) -> Dict[str, Any]:
        """
        Convert tool definition to OpenAI/Ollama function calling schema.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_schema.model_json_schema(),
            },
        }
