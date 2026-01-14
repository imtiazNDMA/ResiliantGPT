import pytest
import os
import tempfile
from unittest.mock import patch

# Add the parent directory to the path
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config
from services import database


class TestDatabase:
    """Test suite for database operations."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def mock_config(self, temp_db_path):
        """Mock Config to use temporary database."""
        with patch.object(Config, "DATABASE_PATH", temp_db_path):
            yield Config

    def test_init_db(self, mock_config):
        """Test database initialization."""
        database.init_db()
        # Check if table exists by trying to insert
        conv_id = "test_init"
        data = {
            "title": "Test Init",
            "history": [],
            "last_updated": 1234567890,
            "mode": "general",
        }
        database.save_conversation(conv_id, data)
        retrieved = database.get_conversation(conv_id)
        assert retrieved is not None
        assert retrieved["title"] == "Test Init"

    def test_save_and_get_conversation(self, mock_config):
        """Test saving and retrieving conversations."""
        database.init_db()

        conv_id = "test_save_get"
        data = {
            "title": "Test Conversation",
            "history": [{"user": "Hello", "bot": "Hi there!", "timestamp": 1234567890}],
            "last_updated": 1234567890,
            "mode": "pakistan",
        }

        # Save conversation
        database.save_conversation(conv_id, data)

        # Retrieve conversation
        retrieved = database.get_conversation(conv_id)

        assert retrieved is not None
        assert retrieved["id"] == conv_id
        assert retrieved["title"] == "Test Conversation"
        assert len(retrieved["history"]) == 1
        assert retrieved["history"][0]["user"] == "Hello"
        assert retrieved["history"][0]["bot"] == "Hi there!"
        assert retrieved["mode"] == "pakistan"
