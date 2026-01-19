import concurrent.futures
import uuid
import time
import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)

class TaskQueue:
    """
    Manages background tasks using a ThreadPoolExecutor.
    """
    def __init__(self, max_workers: int = 2):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def submit_task(self, func: Callable, *args, **kwargs) -> str:
        """
        Submit a task to the background queue.
        Returns the task_id.
        """
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "status": "processing",
            "submitted_at": time.time(),
            "result": None,
            "error": None
        }
        
        def task_wrapper():
            try:
                result = func(*args, **kwargs)
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["result"] = result
                self.tasks[task_id]["completed_at"] = time.time()
                logger.info(f"Task {task_id} completed successfully")
            except Exception as e:
                self.tasks[task_id]["status"] = "failed"
                self.tasks[task_id]["error"] = str(e)
                self.tasks[task_id]["completed_at"] = time.time()
                logger.error(f"Task {task_id} failed: {e}")

        self.executor.submit(task_wrapper)
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a specific task.
        """
        return self.tasks.get(task_id)

    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """
        Remove tasks older than max_age_seconds from memory.
        """
        now = time.time()
        to_remove = []
        for tid, info in self.tasks.items():
            if info["status"] in ["completed", "failed"]:
                completed_at = info.get("completed_at", 0)
                if now - completed_at > max_age_seconds:
                    to_remove.append(tid)
        
        for tid in to_remove:
            del self.tasks[tid]

# Global instance
task_queue = TaskQueue()
