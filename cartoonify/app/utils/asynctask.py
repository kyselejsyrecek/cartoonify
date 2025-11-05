import concurrent.futures
import functools
import os
import threading
import uuid
from typing import Any, Callable, Dict, Optional, Union

from app.debugging.logging import getLogger


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
    def __init__(self, max_workers: int = 5, logger=None, locks: Optional[Dict[str, threading.Lock]] = None):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, concurrent.futures.Future] = {}
        self._lock = threading.Lock()
        self._log = logger if logger is not None else getLogger(self.__class__.__name__)
        self._log.debug(f"AsyncExecutor initialized with {max_workers} worker threads.")
        # Named lock registry for exclusive task execution semantics.
        self._locks: Dict[str, threading.Lock] = locks or {}

    def add_lock(self, name: str, lock: Optional[threading.Lock] = None):
        """Register a named lock (creates one if not provided)."""
        if lock is None:
            lock = threading.Lock()
        self._locks[name] = lock
        return lock

    def get_lock(self, name: str) -> Optional[threading.Lock]:
        return self._locks.get(name)

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
        self._log.debug("AsyncExecutor shut down.")


# Decorator for instance methods ---
class async_task: # Lowercase because it's meant to be used like a function call, e.g., @async_task
    """Asynchronous task decorator.

    Only submits the (possibly pre-wrapped) method to the AsyncExecutor. Locking, if any,
    is handled entirely by the @exclusive decorator (which must be placed underneath so
    it executes first and returns a wrapped callable containing lock logic executed in
    the worker thread, not at submission time).
    """

    def __init__(self, func):
        self._func = func # Store the original function (can be lock wrapper but handler extra metadata)

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
                # Submit the bound method directly into the AsyncExecutor's pool.
                instance._log.debug(f"Submitting task '{self._func.__name__}' to asynchronous pool.")
                return instance.submit(self._func, instance, *args, **kwargs)

            return wrapper


def exclusive(lock_spec: Union[str, threading.Lock, Callable[[Any], Optional[threading.Lock]]], *, blocking: bool = False):
    """Decorator enforcing exclusive (single-at-a-time) execution using a lock.

    Ordering: place @exclusive BELOW @async_task so that @exclusive runs first and returns a
    wrapper containing the locking logic. @async_task then submits that wrapper unchanged,
    meaning the lock is acquired inside the worker thread (not blocking the caller on submit).

        @async_task
        @exclusive('event', blocking=False)
        def capture(self): ...

    lock_spec:
        - str: name of a lock in the instance's named lock registry (preferred) or an attribute.
        - threading.Lock: the lock object itself.
        - callable(self) -> lock | None: dynamically resolve and return a lock.
    blocking:
        - False: non-blocking acquire; task is skipped if lock cannot be obtained immediately.
        - True: blocks the worker thread until the lock is acquired.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def locked(self, *args, **kwargs):
            # Resolve the lock each execution (allows dynamic replacement if needed).
            self._log.debug(f"Trying to lock task '{func.__name__}' from PID {os.getpid()}.")
            resolved_lock = None
            try:
                if isinstance(lock_spec, str):
                    if hasattr(self, 'get_lock'):
                        resolved_lock = getattr(self, 'get_lock')(lock_spec)  # type: ignore
                    if resolved_lock is None:
                        resolved_lock = getattr(self, lock_spec, None)
                elif callable(lock_spec) and not isinstance(lock_spec, threading.Lock):
                    resolved_lock = lock_spec(self)
                else:
                    resolved_lock = lock_spec  # Might be a Lock or None
            except Exception:
                if hasattr(self, '_log'):
                    self._log.exception(f"Failed to resolve lock for '{func.__name__}'. Aborting task.")
                return None

            if resolved_lock is None:
                # If no lock object is available, abort the task; never run unlocked implicitly.
                if hasattr(self, '_log'):
                    self._log.exception(f"No lock resolved for '{func.__name__}'. Aborting task.")
                return None

            # Try to acquire the lock (blocking or non-blocking per parameter). If acquisition fails or raises,
            # abort the task without executing the wrapped function.
            try:
                acquired = resolved_lock.acquire(blocking=blocking)
            except Exception:
                if hasattr(self, '_log'):
                    self._log.exception(f"Exception while acquiring lock for '{func.__name__}'. Aborting task.")
                return None
            if not acquired:
                # Non-blocking failed to acquire OR lock reported false; skip execution.
                if hasattr(self, '_log'):
                    self._log.info(f"Task '{func.__name__}' skipped: another operation in progress.")
                return None

            try:
                return func(self, *args, **kwargs)
            finally:
                # Release only if we actually acquired (true by construction here).
                try:
                    resolved_lock.release()
                except Exception:
                    if hasattr(self, '_log'):
                        self._log.exception(f"Failed to release lock in '{func.__name__}'.")
        return locked
    return decorator