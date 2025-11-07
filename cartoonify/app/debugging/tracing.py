import sys
import linecache
import functools
from contextlib import contextmanager
from pathlib import Path


def _trace_function(frame, event, arg, output=None, target_code=None, recursive=True, depth=0):
    """Internal trace function that prints executed lines.
    
    :param frame: Current stack frame
    :param event: Event type ('call', 'line', 'return', etc.)
    :param arg: Event argument
    :param output: File-like object to write to (default: sys.stdout)
    :param target_code: Target code object to trace (for non-recursive mode)
    :param recursive: If True, trace all called functions; if False, trace only target code
    :param depth: Current call depth (for indentation)
    :return: Trace function for continued tracing
    """
    if output is None:
        output = sys.stdout
    
    if event == "call":
        # Increase depth when entering a new function.
        return lambda f, e, a: _trace_function(f, e, a, output, target_code, recursive, depth + 1)
    elif event == "return":
        # Decrease depth when exiting a function.
        return lambda f, e, a: _trace_function(f, e, a, output, target_code, recursive, max(0, depth - 1))
    elif event == "line":
        # Non-recursive mode: only trace the target code object.
        if not recursive and target_code is not None and frame.f_code != target_code:
            return lambda f, e, a: _trace_function(f, e, a, output, target_code, recursive, depth)
        
        lineno = frame.f_lineno
        filename = frame.f_code.co_filename
        
        # Skip tracing internal files (tracing.py itself and contextlib.py).
        if filename.endswith('/tracing.py') or filename.endswith('\\tracing.py'):
            return lambda f, e, a: _trace_function(f, e, a, output, target_code, recursive, depth)
        
        # Get relative path if inside project.
        try:
            filepath = Path(filename)
            if filepath.is_absolute():
                # Try to make it relative to current working directory.
                try:
                    filepath = filepath.relative_to(Path.cwd())
                except ValueError:
                    # If not relative to cwd, just use the filename.
                    filepath = filepath.name
            filename = str(filepath)
        except Exception:
            pass
        
        line = linecache.getline(frame.f_code.co_filename, lineno).strip()
        indent = '+' * max(1, depth)
        output.write(f"{indent} {filename}:{lineno}: {line}\n")
        output.flush()
    
    return lambda f, e, a: _trace_function(f, e, a, output, target_code, recursive, depth)


class trace:
    """Decorator and context manager to trace execution line-by-line.
    
    Prints each executed line similar to Bash's 'set -x'.
    
    Usage as decorator:
        @trace
        def my_function(a, b):
            x = a + b
            return x
        
        @trace(output=sys.stderr, recursive=False)
        def another_function():
            pass
    
    Usage as context manager:
        with trace():
            x = 1 + 2
            y = x * 3
            print(y)
        
        with trace(output=open('trace.log', 'w'), recursive=False):
            some_function()
    
    Usage as wrapper:
        result = trace(my_function)(arg1, arg2)
    """
    
    def __init__(self, func=None, *, output=None, recursive=True):
        """Initialize trace decorator/context manager.
        
        :param func: Function to decorate (provided automatically when used as @trace)
        :param output: File-like object to write trace output to (default: sys.stdout)
        :param recursive: If True, trace all called functions; if False, trace only the decorated function
        """
        self.func = func
        self.output = output
        self.recursive = recursive
        self.old_trace = None
    
    def __call__(self, *args, **kwargs):
        """Called when used as decorator or when calling decorated function."""
        # If func is None, we're being called with arguments to create a decorator.
        if self.func is None:
            # First argument should be the function to decorate.
            if len(args) == 1 and callable(args[0]) and not kwargs:
                # Being used as @trace(...)(func)
                return trace(args[0], output=self.output, recursive=self.recursive)
            else:
                raise TypeError('trace() takes a callable as first argument when called')
        
        # We have a function, so we're being called to execute it with tracing.
        # For non-recursive mode, we need the code object of the function to trace.
        target_code = None
        if not self.recursive:
            target_code = self.func.__code__
        
        trace_func = lambda frame, event, arg: _trace_function(frame, event, arg, self.output, target_code, self.recursive, 0)
        
        old_trace = sys.gettrace()
        sys.settrace(trace_func)
        try:
            return self.func(*args, **kwargs)
        finally:
            sys.settrace(old_trace)
    
    def __enter__(self):
        """Enter context manager - start tracing."""
        import inspect
        target_code = None
        if not self.recursive:
            # Get the code object of the calling frame.
            target_code = inspect.currentframe().f_back.f_code
        
        trace_func = lambda frame, event, arg: _trace_function(frame, event, arg, self.output, target_code, self.recursive, 0)
        self.old_trace = sys.gettrace()
        sys.settrace(trace_func)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - stop tracing."""
        sys.settrace(self.old_trace)
        return False


@contextmanager
def suppress_tracing():
    """Context manager to temporarily suppress tracing.
    
    Useful to prevent tracing of internal functions while keeping outer function traced.
    
    Usage:
        @trace
        def outer_function():
            do_something()  # This will be traced
            
            with suppress_tracing():
                internal_function()  # This will NOT be traced
            
            do_something_else()  # This will be traced again
    """
    old_trace = sys.gettrace()
    sys.settrace(None)
    try:
        yield
    finally:
        sys.settrace(old_trace)
