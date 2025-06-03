import concurrent.futures
import functools


class AsyncExecutor:
    def __init__(self, max_workers=5):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        #print(f"ThreadPoolExecutor initialized with {max_workers} threads.")

    def submit_task(self, func, *args, **kwargs):
        return self.executor.submit(func, *args, **kwargs)

    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait)
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
        This method is called when the attribute is accessed on an instance or class.
        'instance' is the object instance (e.g., service in service.long_running_task)
        'owner' is the class (e.g., MyService)
        """
        if instance is None:
            # Accessing through the class (e.g., MyService.long_running_task)
            return self._func
        else:
            # Accessing through an instance (e.g., service.long_running_task)
            # Create a wrapped function that uses the instance's executor
            @functools.wraps(self._func)
            def wrapper(*args, **kwargs):
                if not hasattr(instance, '_async_executor') or not isinstance(instance._async_executor, AsyncExecutor):
                    raise RuntimeError("AsyncExecutor not initialized for this instance. Call init_async_executor in __init__.")
                #print(f"Submitting task '{self._func.__name__}' from instance to pool.")
                # We need to pass the instance's method, not just the raw function
                # The _func itself will receive 'self' as its first argument
                return instance._async_executor.submit_task(self._func, instance, *args, **kwargs)
            return wrapper