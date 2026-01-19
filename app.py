from flask import Flask, render_template, request, jsonify, session
import time
import base64
import os
import secrets
import logging
import json
import threading
import hashlib
from functools import lru_cache
import signal
import sys
from collections import defaultdict
from typing import Dict, Any, List, Tuple, Optional, Union
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from config import Config
from controllers import process_chat_request
from services import database
from services.vector_store import VectorStore
from utils.performance_monitor import (
    get_performance_report,
    performance_monitor,
    monitor_request,
)


# Configure structured JSON logging
class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record):
        try:
            log_entry = {
                "timestamp": self.formatTime(record, self.default_time_format),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)

            # Add extra fields if present
            if hasattr(record, "extra_fields"):
                log_entry.update(record.extra_fields)

            return json.dumps(log_entry, default=str)
        except Exception as e:
            # Fallback to basic logging if JSON formatting fails
            return f"{record.levelname}: {record.getMessage()} (Logging error: {e})"


# Setup logging
json_formatter = JSONFormatter()
console_handler = logging.StreamHandler()
console_handler.setFormatter(json_formatter)

file_handler = logging.FileHandler("resiliencegpt.log", mode="a")
file_handler.setFormatter(json_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
app.config["DEBUG"] = Config.DEBUG
app.config["TESTING"] = Config.TESTING


# Request tracing
@app.before_request
def before_request():
    """Log incoming requests"""
    request.start_time = time.time()
    logger.info(
        "Request started",
        extra={
            "extra_fields": {
                "method": request.method,
                "url": request.url,
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get("User-Agent"),
                "content_length": request.content_length,
            }
        },
    )


@app.after_request
def after_request(response):
    """Log completed requests with timing"""
    try:
        if hasattr(request, "start_time"):
            duration = time.time() - request.start_time
        else:
            duration = 0

        # Safely get response length without consuming stream or large data
        # For static files, content_length is usually set
        response_length = response.content_length or 0

        logger.info(
            "Request completed",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "url": request.url,
                    "status_code": response.status_code,
                    "duration": duration,
                    "response_length": response_length,
                }
            },
        )
    except Exception as e:
        # Prevent logging errors from affecting the response
        app.logger.error(f"Error in after_request logging: {e}")

    return response


os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# File upload validation constants
ALLOWED_EXTENSIONS = {"pdf", "txt", "docx", "csv", "xls", "xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file


# Rate limiting
class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(self):
        self.requests = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(
        self, key: str, limit: int = 100, window: int = 60, check_only: bool = False
    ) -> bool:
        """Check if request is allowed under rate limit"""
        now = time.time()
        with self._lock:
            # Clean old requests
            self.requests[key] = [
                req_time for req_time in self.requests[key] if now - req_time < window
            ]

            allowed = len(self.requests[key]) < limit

            if allowed and not check_only:
                self.requests[key].append(now)

            return allowed


rate_limiter = RateLimiter()


# Response caching
class ResponseCache:
    """Simple in-memory response cache with TTL"""

    def __init__(self, max_size: int = 1000, ttl: int = 300):  # 5 minutes TTL
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl
        self._lock = threading.Lock()

    def _get_key(self, data: dict) -> str:
        """Generate cache key from request data"""
        # Create a deterministic key from relevant fields
        key_data = {
            "message": data.get("message", ""),
            "mode": data.get("mode", "general"),
            "generate_image": data.get("generate_image", False),
        }
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if valid"""
        with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() - entry["timestamp"] < self.ttl:
                    logger.info(f"Cache hit for key: {key[:8]}...")
                    return entry["response"]
                else:
                    # Expired, remove it
                    del self.cache[key]
        return None

    def set(self, key: str, response: Dict[str, Any]):
        """Cache a response"""
        with self._lock:
            # Clean expired entries if cache is full
            if len(self.cache) >= self.max_size:
                current_time = time.time()
                self.cache = {
                    k: v
                    for k, v in self.cache.items()
                    if current_time - v["timestamp"] < self.ttl
                }

            self.cache[key] = {"response": response, "timestamp": time.time()}
            logger.info(f"Cached response for key: {key[:8]}...")

    def clear(self):
        """Clear all cached responses"""
        with self._lock:
            self.cache.clear()
            logger.info("Response cache cleared")


response_cache = ResponseCache()


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_file(file: FileStorage) -> bool:
    """Validate uploaded file for security and size"""
    if not file or not file.filename:
        raise ValueError("No file provided")

    if not allowed_file(file.filename):
        raise ValueError(
            f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )

    # Additional security: check for malicious filenames
    secure_filename(file.filename)

    return True


# Global VectorStore instances - loaded once at startup to avoid per-request loading
vector_store_instances = {}


def initialize_vector_stores():
    """Pre-load VectorStore instances to avoid per-request model loading"""
    global vector_store_instances
    try:
        print("Initializing VectorStore instances...")
        vector_store_instances["pakistan"] = VectorStore(mode="pakistan")
        vector_store_instances["general"] = VectorStore(mode="general")
        print("VectorStore instances initialized successfully")
    except Exception as e:
        print(f"Failed to initialize VectorStore: {e}")
        raise


# Initialize VectorStore instances at startup
initialize_vector_stores()


def conversations(
    conv_id: str, user_message: str, mode: str, type: str, generate_image: bool = False
) -> Tuple[str, Optional[str], str]:
    """
    Handle conversation flow including message processing, LLM response generation, and optional image generation.

    Args:
        conv_id: Unique conversation identifier
        user_message: User's input message
        mode: Conversation mode ('general' or 'pakistan')
        type: Message type ('normal' or other)
        generate_image: Whether to generate an image response

    Returns:
        Tuple of (conversation_id, image_base64, bot_response)
    """
    logger.info(
        f"Processing conversation {conv_id} in {mode} mode, generate_image={generate_image}"
    )
    # Load conversation from DB
    current_conv = database.get_conversation(conv_id)

    if not current_conv:
        title = user_message[:30] if type == "normal" else "Audio_" + user_message[:25]
        current_conv = {
            "id": conv_id,
            "title": title,
            "history": [],
            "last_updated": time.time(),
            "mode": mode,
        }

    # Update last_updated
    current_conv["last_updated"] = time.time()

    # Add user message
    message_entry = {"user": user_message, "timestamp": time.time()}

    current_conv["history"].append(message_entry)

    # Prepare history for context (last 3 messages)
    cleaned_history = [
        {k: v for k, v in entry.items() if k != "image"}
        for entry in current_conv["history"][-3:]
    ]

    # Get the appropriate VectorStore instance
    vector_store = vector_store_instances.get(mode, vector_store_instances["general"])

    vector_store = vector_store_instances.get(mode, vector_store_instances["general"])

    bot_response = process_chat_request(
        user_message,
        "search",
        mode=mode,
        chat_history=cleaned_history,
        vector_store=vector_store,
    )
    current_conv["history"][-1]["bot"] = bot_response

    image_base64 = None
    if generate_image:
        image_base64 = process_chat_request(
            user_text=user_message,
            action="image",
            mode=mode,
            chat_history=cleaned_history,
            vector_store=vector_store,
        )
        if image_base64:
            current_conv["history"][-1]["image"] = image_base64

    if len(current_conv["history"]) == 1:
        current_conv["title"] = user_message[:30]

    # Save back to DB
    database.save_conversation(conv_id, current_conv)

    return conv_id, image_base64, bot_response


@app.route("/")
def home() -> str:
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@monitor_request("POST", "/api/chat")
def chat() -> Union[Tuple[str, int], Dict[str, Any]]:
    """
    Handle chat message requests.

    Expects JSON payload with:
    - message: User's text message
    - conversation_id: Optional conversation identifier
    - mode: 'general' or 'pakistan'
    - generate_image: Optional boolean for image generation

    Returns:
        JSON response with bot reply and conversation data
    """
    # Rate limiting: 50 requests per minute per IP
    client_ip = request.remote_addr or "unknown"
    if not rate_limiter.is_allowed(f"chat:{client_ip}", limit=50, window=60):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    try:
        logger.info("Received chat request")
        data = request.get_json()

        if not data:
            logger.warning("No JSON data received in chat request")
            return jsonify({"error": "Invalid JSON data"}), 400

        user_message = data.get("message")
        conversation_id = data.get("conversation_id")
        mode = data.get("mode", "general")
        generate_image = data.get("generate_image", False)

        if len(user_message) > 10000:  # Reasonable message length limit
            logger.warning(f"Message too long: {len(user_message)} characters")
            return jsonify({"error": "Message too long (max 10000 characters)"}), 400

        # Validate and normalize mode
        mode = mode.lower() if mode else "general"
        if "pakistan" in mode:
            mode = "pakistan"
        else:
            mode = "general"

        logger.info(
            f"Processing chat request: mode={mode}, generate_image={generate_image}, message_length={len(user_message)}"
        )

        # Check cache for identical requests (only for non-conversation-specific requests)
        cache_key = None
        cached_response = None
        if not conversation_id and not generate_image:
            # Only cache requests without conversation context and no image generation
            cache_key = response_cache._get_key(data)
            cached_response = response_cache.get(cache_key)
            if cached_response:
                logger.info("Returning cached response")
                return jsonify(cached_response)

        conv_id, image_base64, bot_response = conversations(
            conv_id=conversation_id,
            user_message=user_message,
            mode=mode,
            type="normal",
            generate_image=generate_image,
        )

        # Cache the response if it was cacheable
        if cache_key and not conversation_id and not generate_image:
            response_data = {
                "response": bot_response,
                "conversation_id": conv_id,
                "mode": mode,
                "image": image_base64,
            }
            response_cache.set(cache_key, response_data)

        logger.info(f"Chat request processed successfully for conversation {conv_id}")
        return jsonify(
            {
                "response": bot_response,
                "conversation_id": conv_id,
                "mode": mode,
                "image": image_base64,
            }
        )

    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    return jsonify(
        {
            "response": bot_response,
            "conversation_id": conv_id,
            "mode": mode,
            "image": image_base64,
        }
    )


@app.route("/chat-audio", methods=["POST"])
@monitor_request("POST", "/chat-audio")
def chat_audio() -> Union[Tuple[str, int], Dict[str, Any]]:
    """
    Handle audio message requests.

    Expects JSON payload with:
    - audio: Base64 encoded audio data
    - conversation_id: Optional conversation identifier
    - mode: 'general' or 'pakistan'
    - generate_image: Optional boolean for image generation

    Returns:
        JSON response with transcribed text, bot reply, and audio data
    """
    # Rate limiting: 20 audio requests per minute per IP (more expensive)
    client_ip = request.remote_addr or "unknown"
    if not rate_limiter.is_allowed(f"audio:{client_ip}", limit=20, window=60):
        logger.warning(f"Rate limit exceeded for audio request from IP: {client_ip}")
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    data = request.get_json()
    audio_base64 = data.get("audio")
    conversation_id = data.get("conversation_id")
    mode = data.get("mode", "general")
    generate_image = data.get("generate_image", False)

    # Validate and normalize mode
    mode = mode.lower() if mode else "general"
    if "pakistan" in mode:
        mode = "pakistan"
    else:
        mode = "general"

    try:
        # Validate base64 format
        audio_data = base64.b64decode(audio_base64)
        if len(audio_data) == 0:
            return jsonify({"error": "Empty audio data"}), 400
        if len(audio_data) > 25 * 1024 * 1024:  # 25MB limit for audio
            return jsonify({"error": "Audio file too large"}), 400
    except Exception:
        return jsonify({"error": "Invalid audio format"}), 400

    audio_data = base64.b64decode(audio_base64)
    data_uri = f"data:audio/wav;base64,{audio_base64}"

    # Need to load history just for context here ??
    # Actually conversations() handles history loading, but newfunc(audio) needs it before.
    # Let's clean this up.

    current_conv = database.get_conversation(conversation_id)
    cleaned_history = []
    if current_conv:
        cleaned_history = [
            {k: v for k, v in entry.items() if k != "image"}
            for entry in current_conv["history"][-3:]
        ]

    user_message = process_chat_request(
        audio_data, "audio", mode=mode, chat_history=cleaned_history, path=audio_base64
    )

    conv_id, image_base64, bot_response = conversations(
        conv_id=conversation_id,
        user_message=user_message,
        mode=mode,
        type="normal",
        generate_image=generate_image,
    )

    return jsonify(
        {
            "reply": bot_response,
            "conversation_id": conv_id,
            "audio_base64": data_uri,
            "user_message": user_message,
            "image": image_base64,
        }
    )


@app.route("/api/new_chat", methods=["POST"])
def new_chat() -> Dict[str, Any]:
    """
    Create a new conversation.

    Expects JSON payload with:
    - mode: 'general' or 'pakistan'

    Returns:
        JSON response with new conversation ID and mode
    """
    data = request.get_json()
    mode = data.get("mode", "general")

    conversation_id = str(int(time.time() * 1000))

    new_conv_data = {
        "title": "New Chat",
        "history": [],
        "last_updated": time.time(),
        "mode": mode,
    }
    database.save_conversation(conversation_id, new_conv_data)

    return jsonify(
        {"status": "success", "conversation_id": conversation_id, "mode": mode}
    )


@app.route("/upload", methods=["POST"])
@monitor_request("POST", "/upload")
def upload_file() -> Union[Tuple[str, int], Dict[str, Any]]:
    """
    Handle document upload and processing.

    Expects form data with:
    - files: Multiple file uploads (PDF, TXT, DOCX, CSV, XLS, XLSX)
    - mode: 'general' or 'pakistan'

    Returns:
        JSON response with processing status and file information
    """
    # Rate limiting: 10 uploads per minute per IP
    client_ip = request.remote_addr or "unknown"
    if not rate_limiter.is_allowed(f"upload:{client_ip}", limit=10, window=60):
        logger.warning(f"Rate limit exceeded for upload from IP: {client_ip}")
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    files = request.files.getlist("files")
    mode = request.form.get("mode", "general")

    logger.info(
        f"Received file upload request with {len(files)} files for mode: {mode}"
    )
    files = request.files.getlist("files")
    mode = request.form.get("mode", "general")

    if not files or all(not file.filename for file in files):
        return jsonify({"error": "No files provided"}), 400

    # Validate all files before processing
    validated_files = []
    validated_names = []
    for file in files:
        try:
            validate_file(file)
            validated_files.append(file)
            validated_names.append(file.filename)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    try:
        # Get the appropriate VectorStore instance
        vector_store = vector_store_instances.get(
            mode, vector_store_instances["general"]
        )

        process_chat_request(
            "message",
            "insert",
            mode=mode,
            chat_history=[],
            files=validated_files,
            vector_store=vector_store,
        )
        return jsonify(
            {
                "status": "success",
                "message": f"File(s) {validated_names} processed successfully",
                "filename": validated_names,
            }
        )

    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500


@app.route("/api/conversations", methods=["GET"])
def get_conversations() -> Dict[str, Any]:
    """
    Retrieve all conversations for the current session.

    Returns:
        JSON response with list of conversations (id, title, last_updated, mode)
    """
    return jsonify({"conversations": database.load_all_conversations()})


@app.route("/api/conversation/<conversation_id>", methods=["GET"])
def get_conversation_by_id(conversation_id) -> Union[Tuple[str, int], Dict[str, Any]]:
    """
    Retrieve full details for a specific conversation by ID.
    """
    try:
        conv = database.get_conversation(conversation_id)
        if not conv:
            logger.warning(f"Conversation {conversation_id} not found")
            return jsonify({"error": "Conversation not found"}), 404
        return jsonify(conv)
    except Exception as e:
        logger.error(f"Error retrieving conversation {conversation_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/current_conversation", methods=["GET"])
def get_current_conversation() -> Union[Tuple[str, int], Dict[str, Any]]:
    """
    Retrieve the most recent conversation.

    Returns:
        JSON response with full conversation data or error if no conversations exist
    """
    # This endpoint seems mostly used to restore session on reload
    # Since we don't rely on cookie session for ID anymore, the client needs to track ID
    # But if client forgets, we can return latest
    all_convs = database.load_all_conversations()
    if not all_convs:
        return jsonify({"error": "No conversations"}), 404

    latest_id = max(all_convs.keys(), key=lambda k: all_convs[k]["last_updated"])
    full_conv = database.get_conversation(latest_id)

    return jsonify({"conversation_id": latest_id, "conversation": full_conv})


@app.route("/api/delete_chat", methods=["POST"])
def delete_chat() -> Union[Tuple[str, int], Dict[str, Any]]:
    """
    Delete a conversation by ID.

    Expects JSON payload with:
    - conversation_id: ID of conversation to delete

    Returns:
        JSON response with deletion status
    """
    conversation_id = request.get_json().get("conversation_id")
    if not conversation_id:
        return jsonify({"error": "Missing conversation ID"}), 400

    database.delete_conversation(conversation_id)
    return jsonify({"status": "success", "message": "Chat deleted"})


@app.route("/api/performance", methods=["GET"])
def get_performance() -> Union[Tuple[str, int], Dict[str, Any]]:
    """Get performance metrics and system stats"""
    try:
        report = get_performance_report()
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": f"Failed to get performance data: {str(e)}"}), 500


@app.route("/api/performance/clear", methods=["POST"])
def clear_performance_metrics() -> Union[Tuple[str, int], Dict[str, Any]]:
    """Clear performance metrics data"""
    try:
        metric_name = request.get_json().get("metric_name")
        performance_monitor.clear_metrics(metric_name)
        return jsonify({"status": "success", "message": "Metrics cleared"})
    except Exception as e:
        return jsonify({"error": f"Failed to clear metrics: {str(e)}"}), 500


@app.route("/api/cache/clear", methods=["POST"])
def clear_caches() -> Dict[str, Any]:
    """Clear all application caches"""
    try:
        # Clear response cache
        response_cache.clear()

        # Clear LLM caches
        from services.llm_service import LLMService

        llm_service = LLMService()
        llm_service.clear_caches()

        # Clear vector store caches
        for vs in vector_store_instances.values():
            # Clear embedding cache (this is a class variable)
            VectorStore._embedding_cache.clear()

        return jsonify(
            {
                "status": "success",
                "message": "All caches cleared",
                "cleared": ["response_cache", "llm_cache", "embedding_cache"],
            }
        )
    except Exception as e:
        logger.error(f"Failed to clear caches: {str(e)}")
        return jsonify({"error": f"Failed to clear caches: {str(e)}"}), 500


@app.route("/api/cache/stats", methods=["GET"])
def cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    try:
        stats = {
            "response_cache": {
                "size": len(response_cache.cache),
                "max_size": response_cache.max_size,
            },
            "embedding_cache": {"size": len(VectorStore._embedding_cache)},
        }

        # Try to get LLM cache size
        try:
            from services.llm_service import _response_cache

            stats["llm_cache"] = {"size": len(_response_cache)}
        except:
            stats["llm_cache"] = {"size": "unknown"}

        return jsonify(stats)
    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        return jsonify({"error": f"Failed to get cache stats: {str(e)}"}), 500


@app.route("/api/rate-limit/status", methods=["GET"])
def rate_limit_status() -> Dict[str, Any]:
    """Get current rate limiting status"""
    try:
        client_ip = request.remote_addr or "unknown"
        status = {
            "client_ip": client_ip,
            "limits": {
                "chat": {
                    "allowed": rate_limiter.is_allowed(
                        f"chat:{client_ip}", limit=50, window=60, check_only=True
                    ),
                    "limit": 50,
                    "window": 60,
                },
                "audio": {
                    "allowed": rate_limiter.is_allowed(
                        f"audio:{client_ip}", limit=20, window=60, check_only=True
                    ),
                    "limit": 20,
                    "window": 60,
                },
                "upload": {
                    "allowed": rate_limiter.is_allowed(
                        f"upload:{client_ip}", limit=10, window=60, check_only=True
                    ),
                    "limit": 10,
                    "window": 60,
                },
            },
        }
        return jsonify(status)
    except Exception as e:
        logger.error(f"Failed to get rate limit status: {str(e)}")
        return jsonify({"error": f"Failed to get rate limit status: {str(e)}"}), 500


@app.route("/health", methods=["GET"])
def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for monitoring system status.

    Returns basic health information and system stats.
    """
    try:
        # Check database connectivity
        db_healthy = True
        try:
            database.get_conversation("health_check_test")
        except Exception:
            db_healthy = False

        # Check vector stores
        vector_stores_healthy = True
        try:
            for mode, vs in vector_store_instances.items():
                # Simple health check - try to get collection count
                vs.collection.count()
        except Exception:
            vector_stores_healthy = False

        # System stats
        system_stats = performance_monitor.get_system_stats()

        health_status = {
            "status": (
                "healthy" if (db_healthy and vector_stores_healthy) else "unhealthy"
            ),
            "timestamp": time.time(),
            "version": "1.0.0",
            "services": {
                "database": "healthy" if db_healthy else "unhealthy",
                "vector_store": "healthy" if vector_stores_healthy else "unhealthy",
                "llm_service": "healthy",  # Assume healthy if app is running
            },
            "system": system_stats,
            "uptime": time.time() - getattr(app, "start_time", time.time()),
        }

        status_code = 200 if health_status["status"] == "healthy" else 503
        return jsonify(health_status), status_code

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return (
            jsonify({"status": "unhealthy", "error": str(e), "timestamp": time.time()}),
            503,
        )


@app.route("/metrics", methods=["GET"])
def prometheus_metrics() -> Union[Tuple[str, int], str]:
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus format for monitoring systems.
    """
    try:
        from utils.performance_monitor import get_prometheus_metrics

        metrics_data = get_prometheus_metrics()
        response = app.response_class(
            response=metrics_data, status=200, mimetype="text/plain; charset=utf-8"
        )
        return response
    except Exception as e:
        logger.error(f"Failed to generate metrics: {str(e)}")
        return "Error generating metrics", 500


# Graceful shutdown handling
shutdown_event = threading.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()

    # Perform cleanup
    try:
        # Clear caches to free memory
        response_cache.clear()

        # Close database connections
        # SQLite connections are automatically closed, but we can log
        logger.info("Performing cleanup before shutdown...")

        # Give some time for ongoing requests to complete
        time.sleep(2)

    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {str(e)}")

    logger.info("Shutdown complete")
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    # Record app start time for uptime tracking
    app.start_time = time.time()
    logger.info("Starting ResilienceGPT application...")

    try:
        app.run(host="0.0.0.0", port=5002, debug=True, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application crashed: {str(e)}")
        sys.exit(1)
    finally:
        signal_handler(signal.SIGTERM, None)
