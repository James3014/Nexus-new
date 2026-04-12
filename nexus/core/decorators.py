import functools
import asyncio
import inspect
import traceback
import time
from typing import Any, Callable, Optional
from nexus.services.metabolism_engine import metabolism

def nexus_metabolize(task_name: Optional[str] = None):
    """
    🛡️ Nexus Global Metabolism Decorator.
    Automatically captures session experience, successes, and failures.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            session_context = {
                "goal": task_name or func.__name__,
                "done": [],
                "errors": []
            }
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                session_context["done"].append({
                    "action": "execute",
                    "status": "success",
                    "duration": f"{duration:.2f}s"
                })
                metabolism.distill(session_context)
                return result
            except BaseException as e:
                duration = time.time() - start_time
                error_msg = f"{type(e).__name__}: {str(e)}"
                session_context["errors"].append({
                    "action": "execute",
                    "status": "fail",
                    "message": error_msg,
                    "traceback": traceback.format_exc(),
                    "duration": f"{duration:.2f}s"
                })
                metabolism.distill(session_context)
                raise e

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            session_context = {
                "goal": task_name or func.__name__,
                "done": [],
                "errors": []
            }
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                session_context["done"].append({
                    "action": "execute",
                    "status": "success",
                    "duration": f"{duration:.2f}s"
                })
                metabolism.distill(session_context)
                return result
            except BaseException as e:
                duration = time.time() - start_time
                error_msg = f"{type(e).__name__}: {str(e)}"
                session_context["errors"].append({
                    "action": "execute",
                    "status": "fail",
                    "message": error_msg,
                    "traceback": traceback.format_exc(),
                    "duration": f"{duration:.2f}s"
                })
                metabolism.distill(session_context)
                raise e

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator
