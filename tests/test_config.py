import pytest
import os
import importlib
from unittest.mock import patch

# Add the parent directory to the path
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestConfig:
    """Test suite for configuration loading."""

    def test_default_config_values(self):
        """Test that Config has expected default values."""
        # Import fresh module
        import config

        importlib.reload(config)
        Config = config.Config

        config_instance = Config()

        assert hasattr(config_instance, "SECRET_KEY")
        assert hasattr(config_instance, "OLLAMA_BASE_URL")
        assert hasattr(config_instance, "OLLAMA_MODEL")
        assert hasattr(config_instance, "DATABASE_PATH")
        assert hasattr(config_instance, "CHROMA_DB_PATH")
        assert hasattr(config_instance, "UPLOAD_FOLDER")

        # Check default values
        assert config_instance.OLLAMA_BASE_URL == "http://localhost:11434"
        assert config_instance.OLLAMA_MODEL == "llama3.1"
        assert config_instance.DATABASE_PATH == "conversations.db"
        assert config_instance.CHROMA_DB_PATH == "./chroma_local_db"
        assert config_instance.UPLOAD_FOLDER == "uploads"

    def test_env_var_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "SECRET_KEY": "test_secret",
            "OLLAMA_BASE_URL": "http://test:1234",
            "OLLAMA_MODEL": "test_model",
            "DATABASE_PATH": "/tmp/test.db",
            "CHROMA_DB_PATH": "/tmp/chroma",
        }

        with patch.dict(os.environ, env_vars):
            # Reload module to pick up env vars
            import config

            importlib.reload(config)
            ConfigClass = config.Config
            config_instance = ConfigClass()

            assert config_instance.SECRET_KEY == "test_secret"
            assert config_instance.OLLAMA_BASE_URL == "http://test:1234"
            assert config_instance.OLLAMA_MODEL == "test_model"
            assert config_instance.DATABASE_PATH == "/tmp/test.db"
            assert config_instance.CHROMA_DB_PATH == "/tmp/chroma"

    def test_partial_env_override(self):
        """Test that only set env vars override defaults."""
        env_vars = {
            "SECRET_KEY": "partial_secret",
        }

        with patch.dict(os.environ, env_vars):
            # Reload module
            import config

            importlib.reload(config)
            ConfigClass = config.Config
            config_instance = ConfigClass()

            assert config_instance.SECRET_KEY == "partial_secret"
            # Others should be defaults
            assert config_instance.OLLAMA_BASE_URL == "http://localhost:11434"
            assert config_instance.OLLAMA_MODEL == "llama3.1"

    def test_environment_detection(self):
        """Test environment detection and settings."""
        # Test development
        with patch.dict(os.environ, {"FLASK_ENV": "development"}):
            import config

            importlib.reload(config)
            ConfigClass = config.Config
            config_instance = ConfigClass()

            assert config_instance.ENV == "development"
            assert config_instance.DEBUG is True
            assert config_instance.is_development() is True
            assert config_instance.is_production() is False

        # Test production
        with patch.dict(os.environ, {"FLASK_ENV": "production"}):
            import config

            importlib.reload(config)
            ConfigClass = config.Config
            config_instance = ConfigClass()

            assert config_instance.ENV == "production"
            assert config_instance.DEBUG is False
            assert config_instance.is_development() is False
            assert config_instance.is_production() is True

    def test_config_methods(self):
        """Test config utility methods."""
        import config

        importlib.reload(config)
        ConfigClass = config.Config
        config_instance = ConfigClass()

        # Test database URL
        expected_db_url = f"sqlite:///{config_instance.DATABASE_PATH}"
        assert config_instance.get_database_url() == expected_db_url

        # Test upload dir
        upload_dir = config_instance.get_upload_dir()
        assert os.path.isabs(upload_dir)
        assert upload_dir.endswith(config_instance.UPLOAD_FOLDER)

    def test_env_var_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "SECRET_KEY": "test_secret",
            "OLLAMA_BASE_URL": "http://test:1234",
            "OLLAMA_MODEL": "test_model",
            "DATABASE_PATH": "/tmp/test.db",
            "CHROMA_DB_PATH": "/tmp/chroma",
        }

        with patch.dict(os.environ, env_vars):
            # Reload module to pick up env vars
            import config

            importlib.reload(config)
            ConfigClass = config.Config
            config_instance = ConfigClass()

            assert config_instance.SECRET_KEY == "test_secret"
            assert config_instance.OLLAMA_BASE_URL == "http://test:1234"
            assert config_instance.OLLAMA_MODEL == "test_model"
            assert config_instance.DATABASE_PATH == "/tmp/test.db"
            assert config_instance.CHROMA_DB_PATH == "/tmp/chroma"

    def test_partial_env_override(self):
        """Test that only set env vars override defaults."""
        env_vars = {
            "SECRET_KEY": "partial_secret",
        }

        with patch.dict(os.environ, env_vars):
            # Reload module
            import config

            importlib.reload(config)
            ConfigClass = config.Config
            config_instance = ConfigClass()

            assert config_instance.SECRET_KEY == "partial_secret"
            # Others should be defaults
            assert config_instance.OLLAMA_BASE_URL == "http://localhost:11434"
            assert config_instance.OLLAMA_MODEL == "llama3.1"
