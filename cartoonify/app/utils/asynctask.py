import concurrent.futures
import functools
import threading
import uuid
from typing import Any, Callable, Dict, Optional


class TaskRef:
    """
    Lightweight reference to a task. In-process it wraps a Future-like object;
    across process boundaries it pickles down to just task_id (str).
    """
    __slots__ = ("id", "_future")

    def __init__(self, task_id: str, future: concurrent.futures.Future):
        self.id = task_id
        self._future = future

    # Convenience methods for in-process callers
    def result(self, timeout: Optional[float] = None) -> Any:
        return self._future.result(timeout=timeout)

    def exception(self, timeout: Optional[float] = None) -> BaseException | None:
        return self._future.exception(timeout=timeout)

    def done(self) -> bool:
        return self._future.done()

    def add_done_callback(self, fn: Callable[[concurrent.futures.Future], None]) -> None:
        self._future.add_done_callback(fn)

    def __reduce__(self):
        """
        When crossing a multiprocessing boundary, reduce to a plain, picklable string.
        This avoids serializing the internal Future containing locks (RLock).
        """
        return (str, (self.id,))


class AsyncExecutor:
    """
    Parallel executor: runs tasks on a ThreadPoolExecutor and keeps a registry
    of submitted futures by task_id. Designed to work both in-process and
    across multiprocessing boundaries (via TaskRef pickling to task_id).
    """

    def __init__(self, max_workers: int = 5):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, concurrent.futures.Future] = {}
        self._lock = threading.Lock()
        #print(f"ThreadPoolExecutor initialized with {max_workers} threads.")

    def submit(self, fn: Callable, *args, **kwargs) -> TaskRef:
        task_id = uuid.uuid4().hex
        fut = self._executor.submit(fn, *args, **kwargs)
        with self._lock:
            self._futures[task_id] = fut

        def _cleanup(_):
            with self._lock:
                self._futures.pop(task_id, None)

        fut.add_done_callback(_cleanup)
        return TaskRef(task_id, fut)

    # Methods safe to call via Manager-exposed Workflow
    def task_wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        fut = self._get_future(task_id)
        return fut.result(timeout=timeout)

    def task_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        fut = self._get_future(task_id)
        return fut.result(timeout=timeout)

    def task_exception(self, task_id: str, timeout: Optional[float] = None) -> BaseException | None:
        fut = self._get_future(task_id)
        return fut.exception(timeout=timeout)

    def is_task_done(self, task_id: str) -> bool:
        with self._lock:
            fut = self._futures.get(task_id)
        return True if fut is None else fut.done()

    def _get_future(self, task_id: str) -> concurrent.futures.Future:
        with self._lock:
            fut = self._futures.get(task_id)
        if fut is None:
            raise KeyError(f"Unknown or already collected task_id: {task_id}")
        return fut

    def shutdown(self, wait: bool = True):
        self._executor.shutdown(wait=wait)
        #print("ThreadPoolExecutor has been shut down.")


# Decorator for instance methods ---
class async_task: # Lowercase because it's meant to be used like a function call, e.g., @async_task
    def __init__(self, func):
        self._func = func # Store the original function

    def __set_name__(self, owner, name):
        # This method is called when the attribute is assigned to a class.
        # 'owner' is the class (e.g., MyService)
        # 'name' is the attribute name (e.g., 'long_running_task')
        self._owner = owner
        self._name = name

    def __get__(self, instance, owner):
        """
        Descriptor binding. When accessed via instance, return a wrapper that
        enqueues the call into the instance's serialized AsyncExecutor.
        """
        if instance is None:
            # Accessing through the class (e.g., MyService.long_running_task)
            return self._func
        else:
            # Accessing through an instance (e.g., service.long_running_task)
            # Create a wrapped function that uses the instance's executor
            @functools.wraps(self._func)
            def wrapper(*args, **kwargs):
                if not isinstance(instance, AsyncExecutor):
                    raise RuntimeError("Instance must inherit from AsyncExecutor to use @async_task.")
                #print(f"Submitting task '{self._func.__name__}' to asynchronous pool.")
                # Submit the bound method directly into the AsyncExecutor's pool
                return instance.submit(self._func, instance, *args, **kwargs)

            return wrapper