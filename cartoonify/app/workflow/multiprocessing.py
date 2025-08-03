import multiprocessing
import os
import signal
import sys
import logging
from abc import ABC, abstractmethod

from multiprocessing.managers import BaseManager
from app.debugging.logging import getLogger  # Import our enhanced getLogger


# Global event for signaling processes to exit.
# Do not access directly from subprocesses! Must always be obtained from event_proxy.
exit_event = multiprocessing.Event()
halt_event = multiprocessing.Event()


class ProcessInterface(ABC):
    """Abstract base class for all processes that can be started via multiprocessing."""
    
    @staticmethod
    @abstractmethod
    def hook_up(event_service, logger, *args, **kwargs):
        """Hook up the process with event service and logger.
        
        :param event_service: Event service proxy
        :param logger: Logger instance for this process
        :param args: Additional positional arguments
        :param kwargs: Additional keyword arguments
        """
        pass


# Custom Manager for registering our service
class EventManager(BaseManager):
    pass


class ProcessManager:
    """Manages execution and termination of subprocesses.
    """

    def __init__(self, manager_address, manager_authkey):
        self._logger = getLogger(self.__class__.__name__)
        self._subprocesses = []
        self._manager_address = manager_address
        self._manager_authkey = manager_authkey

    def _pipe_reader(self, pipe_read_fd, logger, log_level):
        """Generic pipe reader for stdout/stderr capture.
        
        :param pipe_read_fd: File descriptor to read from
        :param logger: Logger instance to write to
        :param log_level: Logging level (logging.INFO for stdout, logging.ERROR for stderr)
        """
        try:
            with os.fdopen(pipe_read_fd, 'r') as pipe_reader:
                for line in pipe_reader:
                    if line.strip():
                        # Log the raw content without additional prefix
                        logger.log(log_level, line.rstrip())
        except:
            pass


    def start_process(self, process_class, *args, capture_stdout=True, capture_stderr=True, filter_ansi=True, custom_filter=None, **kwargs):
        """Start a new process using a ProcessInterface subclass.
        
        :param process_class: Class that inherits from ProcessInterface
        :param capture_stdout: Whether to capture stdout from child process (default: True)
        :param capture_stderr: Whether to capture stderr from child process (default: True)
        :param filter_ansi: Whether to filter ANSI escape sequences (default: True)
        :param custom_filter: Custom filter function for log messages (default: None)
        :param args: Additional positional arguments for hook_up
        :param kwargs: Additional keyword arguments for hook_up
        """
        # Validate that the class implements ProcessInterface
        if not issubclass(process_class, ProcessInterface):
            raise ValueError(f"Process class {process_class.__name__} must inherit from ProcessInterface")
        
        # Create logger for this process in the main process
        module_logger = getLogger(process_class.__name__, filter_ansi=filter_ansi, custom_filter=custom_filter)
        
        # Set up pipes for stdout/stderr capture if requested
        stdout_pipe = None
        stderr_pipe = None
        stdout_thread = None
        stderr_thread = None
        
        if capture_stdout or capture_stderr:
            import threading
            
            if capture_stdout:
                stdout_read, stdout_write = os.pipe()
                stdout_pipe = (stdout_read, stdout_write)
                
                stdout_thread = threading.Thread(
                    target=self._pipe_reader, 
                    args=(stdout_read, module_logger, logging.INFO), 
                    daemon=True
                )
                stdout_thread.start()
            
            if capture_stderr:
                stderr_read, stderr_write = os.pipe()
                stderr_pipe = (stderr_read, stderr_write)
                
                stderr_thread = threading.Thread(
                    target=self._pipe_reader, 
                    args=(stderr_read, module_logger, logging.WARNING), 
                    daemon=True
                )
                stderr_thread.start()
        
        p = multiprocessing.Process(target=self._task_wrapper, 
                                    args=(process_class, len(self._subprocesses) + 1, module_logger, args, kwargs, stdout_pipe, stderr_pipe))
        
        # Store process info with pipes for cleanup
        process_info = {
            'process': p,
            'class': process_class,
            'stdout_pipe': stdout_pipe,
            'stderr_pipe': stderr_pipe,
            'stdout_thread': stdout_thread,
            'stderr_thread': stderr_thread
        }
        self._subprocesses.append(process_info)
        p.start()
        
        # Close write ends in parent process
        if stdout_pipe:
            os.close(stdout_pipe[1])
        if stderr_pipe:
            os.close(stderr_pipe[1])
            
        return p

    
    def _task_wrapper(self, process_class, id, module_logger, args, kwargs, stdout_pipe, stderr_pipe):
        """
        The main task executed by each child process.
        """
        # Redirect stdout/stderr if pipes are provided
        if stdout_pipe:
            os.dup2(stdout_pipe[1], 1)  # Redirect stdout to pipe
            os.close(stdout_pipe[0])    # Close read end in child
            os.close(stdout_pipe[1])    # Close write end after dup2
        
        if stderr_pipe:
            os.dup2(stderr_pipe[1], 2)  # Redirect stderr to pipe
            os.close(stderr_pipe[0])    # Close read end in child
            os.close(stderr_pipe[1])    # Close write end after dup2
        
        def signal_handler(signum, frame):
            try:
                # Try to access exit_event through event_proxy.
                if 'event_proxy' in locals():
                    if event_proxy.exit_event.is_set():
                        return  # Already exiting, return immediately.
                    module_logger.info(f"Child Process {id} ({process_class.__name__}): Received signal {signum}, exiting.")
                    event_proxy.exit_event.set()
            except:
                # Cannot access exit_event, just exit.
                module_logger.info(f"Child Process {id} ({process_class.__name__}): Received signal {signum}, exiting.")
            sys.exit(0)

        # Set up the SIGINT handler for the child process.
        signal.signal(signal.SIGINT, signal_handler)

        module_logger.info(f"Child Process {id} ({process_class.__name__}): Starting. PID: {os.getpid()}")

        # Connect to the parent process's manager.
        # Register the instance directly (without a callable) for client-side access.
        EventManager.register('event_service')
        event_manager = EventManager(address=self._manager_address, authkey=self._manager_authkey)
        try:
            event_manager.connect()
            event_proxy = event_manager.event_service()
        except Exception as e:
            module_logger.error(f"Child Process {id} ({process_class.__name__}): Failed to connect to manager: {e}")
            sys.exit(1)

        try:
            # Call the static hook_up method on the process class
            process_class.hook_up(event_proxy, module_logger, *args, **kwargs)
        finally:
            module_logger.info(f"Child Process {id} ({process_class.__name__}): Exiting.")


    def terminate(self):
        """Terminates all subprocesses.
        """
        self._logger.info('Terminating child processes...')
        # Attempt to gracefully terminate all child processes.
        for process_info in self._subprocesses:
            p = process_info['process']
            process_class = process_info['class']
            if p.is_alive():
                p.terminate() # Request child to terminate.
                p.join(timeout=1) # Wait for termination with a timeout.
                if p.is_alive():
                    # If child hasn't terminated, forcibly kill it.
                    self._logger.warning(f"Subprocess {p.pid} ({process_class.__name__}) did not terminate gracefully, killing.")
                    os.kill(p.pid, signal.SIGKILL)
            
            # Clean up pipes
            if process_info['stdout_pipe']:
                try:
                    os.close(process_info['stdout_pipe'][0])
                except:
                    pass
            if process_info['stderr_pipe']:
                try:
                    os.close(process_info['stderr_pipe'][0])
                except:
                    pass