import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Configuration class for ResilienceGPT application.

    Loads settings from environment variables with sensible defaults.
    Supports environment-specific configurations (development/production).
    All paths are relative to the application root unless specified as absolute.
    """

    # Environment settings
    ENV: str = os.getenv("FLASK_ENV", "development").lower()
    DEBUG: bool = ENV == "development"
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-dev-key-do-not-use-in-prod")

    # LLM Settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")

    # Database Settings
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "conversations.db")

    # Vector Store Settings
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "./chroma_local_db")

    # Uploads
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH: int = int(
        os.getenv("MAX_CONTENT_LENGTH", "52428800")
    )  # 50MB default

    # Performance settings
    VECTOR_STORE_CACHE_SIZE: int = int(os.getenv("VECTOR_STORE_CACHE_SIZE", "1000"))
    LLM_CACHE_SIZE: int = int(os.getenv("LLM_CACHE_SIZE", "500"))

    @classmethod
    def from_env(cls) -> "Config":
        """Factory method to create config based on environment."""
        return cls()

    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENV == "development"

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENV == "production"

    def get_database_url(self) -> str:
        """Get database connection string."""
        return f"sqlite:///{self.DATABASE_PATH}"

    def get_upload_dir(self) -> str:
        """Get absolute path to upload directory."""
        return os.path.abspath(self.UPLOAD_FOLDER)

    SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-key-do-not-use-in-prod")

    # LLM Settings
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

    # Database Settings
    DATABASE_PATH = os.getenv("DATABASE_PATH", "conversations.db")

    # Vector Store Settings
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_local_db")

    # Uploads
    UPLOAD_FOLDER = "uploads"
