"""System call tracing utilities for debugging.

This module provides tools to trace system calls using the strace utility.
Requires strace to be installed on the system.
"""

import sys
import os
import subprocess
import threading
import contextlib
from functools import wraps

from app.debugging.logging import getLogger

_log = getLogger(__name__)

# Global state for strace process.
_strace_process = None
_strace_thread = None
_strace_active = False


class SyscallTracer:
    """Context manager for system call tracing using strace."""
    
    def __init__(self, enabled=True, output_file=None, filter_syscalls=None, follow_forks=True):
        """Initialize syscall tracer.
        
        :param enabled: Whether tracing is enabled
        :param output_file: File path to write trace output (None for stderr)
        :param filter_syscalls: List of syscall names to trace (e.g., ['read', 'write'])
        :param follow_forks: Whether to follow forked processes
        """
        self.enabled = enabled
        self.output_file = output_file
        self.filter_syscalls = filter_syscalls
        self.follow_forks = follow_forks
        self._strace_process = None
        self._reader_thread = None
        self._reader_tid = None
        self._trace_file = None
    
    def __enter__(self):
        """Start syscall tracing by attaching strace to current process."""
        global _strace_process, _strace_thread, _strace_active
        
        if not self.enabled:
            return self
        
        # Check if strace is available.
        strace_path = self._find_strace()
        if not strace_path:
            _log.error("strace not found. Install with: sudo apt-get install strace")
            return self
        
        # Open output file if specified.
        if self.output_file:
            try:
                self._trace_file = open(self.output_file, 'a')
                _log.info(f"Syscall trace output: {self.output_file}")
            except Exception as e:
                _log.error(f"Failed to open trace output file: {e}")
                return self
        
        # Build strace command.
        pid = os.getpid()
        strace_cmd = [strace_path, '-p', str(pid), '-s', '200', '-v']
        
        # Add follow forks option.
        if self.follow_forks:
            strace_cmd.append('-f')
        
        # Add syscall filter if specified.
        if self.filter_syscalls:
            strace_cmd.extend(['-e', 'trace=' + ','.join(self.filter_syscalls)])
        
        _log.debug(f"Starting strace: {' '.join(strace_cmd)}")
        
        try:
            # Start strace process.
            # strace writes to stderr by default.
            self._strace_process = subprocess.Popen(
                strace_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            _strace_process = self._strace_process
            _strace_active = True
            
            # Start thread to read strace output.
            self._reader_thread = threading.Thread(
                target=self._read_strace_output,
                daemon=True
            )
            self._reader_thread.start()
            _strace_thread = self._reader_thread
            
            _log.info(f"Syscall tracing started (strace PID: {self._strace_process.pid})")
            
        except Exception as e:
            _log.exception(f"Failed to start strace: {e}")
            if self._strace_process:
                self._strace_process.kill()
                self._strace_process = None
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop syscall tracing."""
        global _strace_process, _strace_thread, _strace_active
        
        if not self.enabled or not self._strace_process:
            return
        
        _log.debug("Stopping syscall tracing...")
        _strace_active = False
        
        try:
            # Terminate strace process.
            self._strace_process.terminate()
            self._strace_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _log.warning("strace did not terminate, killing...")
            self._strace_process.kill()
        except Exception as e:
            _log.exception(f"Error stopping strace: {e}")
        
        # Wait for reader thread.
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1)
        
        # Close output file.
        if self._trace_file:
            try:
                self._trace_file.close()
            except:
                pass
            self._trace_file = None
        
        _strace_process = None
        _strace_thread = None
        
        _log.info("Syscall tracing stopped.")
    
    def _find_strace(self):
        """Find strace executable.
        
        :return: Path to strace or None
        """
        for path in ['/usr/bin/strace', '/bin/strace', '/usr/local/bin/strace']:
            if os.path.exists(path):
                return path
        
        # Try using which.
        try:
            result = subprocess.run(['which', 'strace'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        return None
    
    def _read_strace_output(self):
        """Read and log strace output, filtering out the reader thread itself."""
        import re
        
        # Get the TID of this thread.
        # Python threads have native thread IDs accessible via threading.get_native_id().
        try:
            self._reader_tid = threading.get_native_id()
            _log.debug(f"Strace reader thread TID: {self._reader_tid}")
        except AttributeError:
            # Python < 3.8 doesn't have get_native_id(), fallback to no filtering.
            self._reader_tid = None
            _log.warning("Cannot get native thread ID, reader thread will not be filtered from strace output")
        
        try:
            # Read from stderr (strace default output).
            for line in self._strace_process.stderr:
                if not _strace_active:
                    break
                
                line = line.rstrip()
                if not line:
                    continue
                
                # Filter out lines from the reader thread itself to avoid feedback loop.
                if self._reader_tid is not None:
                    # strace format: [pid  1273] syscall(...)
                    # Extract pid from the line.
                    match = re.match(r'^\[pid\s+(\d+)\]', line)
                    if match:
                        line_tid = int(match.group(1))
                        if line_tid == self._reader_tid:
                            # Skip this line, it's from the reader thread.
                            continue
                
                # Format as [STRACE] prefix.
                output_line = f"[STRACE] {line}\n"
                
                # Write to file or stderr.
                if self._trace_file:
                    self._trace_file.write(output_line)
                    self._trace_file.flush()
                else:
                    sys.stderr.write(output_line)
                    sys.stderr.flush()
        
        except Exception as e:
            if _strace_active:
                _log.exception(f"Error reading strace output: {e}")


@contextlib.contextmanager
def strace(enabled=True, output_file=None, filter_syscalls=None, follow_forks=True):
    """Context manager for syscall tracing.
    
    Usage:
        with strace(filter_syscalls=['read', 'write']):
            # Code to trace
            do_something()
    
    :param enabled: Whether tracing is enabled
    :param output_file: File path to write trace output (None for stderr)
    :param filter_syscalls: List of syscall names to trace (None for all)
    :param follow_forks: Whether to follow forked processes
    """
    tracer = SyscallTracer(
        enabled=enabled,
        output_file=output_file,
        filter_syscalls=filter_syscalls,
        follow_forks=follow_forks
    )
    with tracer:
        yield tracer


def strace_decorator(enabled=True, output_file=None, filter_syscalls=None, follow_forks=True):
    """Decorator for syscall tracing.
    
    Usage:
        @strace_decorator(filter_syscalls=['read', 'write'])
        def my_function():
            # Code to trace
            pass
    
    :param enabled: Whether tracing is enabled
    :param output_file: File path to write trace output (None for stderr)
    :param filter_syscalls: List of syscall names to trace (None for all)
    :param follow_forks: Whether to follow forked processes
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with strace(
                enabled=enabled,
                output_file=output_file,
                filter_syscalls=filter_syscalls,
                follow_forks=follow_forks
            ):
                return func(*args, **kwargs)
        return wrapper
    return decorator
