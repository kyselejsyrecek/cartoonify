import logging
import multiprocessing
import os
import signal
import sys
import threading
from abc import ABC, abstractmethod

from multiprocessing.managers import BaseManager, dispatch, listener_client, NamespaceProxy

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


# Custom Manager for registering our services
class EventManager(BaseManager):
    _server = None
    _manager_address = None
    _manager_authkey = None
    _worker = None
    _log = getLogger('EventManager')
    
    @classmethod
    def start(cls, manager_address, manager_authkey):
        """Initialize and start the event manager server process."""
        cls._manager_address = manager_address
        cls._manager_authkey = manager_authkey
        event_manager = cls(manager_address, manager_authkey)
        cls._server = event_manager.get_server()
        # Start the manager server in a separate thread.
        # This prevents the parent's main loop from being blocked by the manager.
        cls._worker = threading.Thread(target=cls._server.serve_forever)
        cls._worker.start()
    
    @classmethod
    def terminate(cls):
        """Terminate the event manager process."""
        try:
            if cls._worker and cls._worker.is_alive():
                cls._log.debug('Terminating event manager...')
                client = listener_client['pickle'][1]
                # address and authkey same as when started the manager
                connection = client(address=cls._manager_address, authkey=cls._manager_authkey)
                dispatch(connection, None, 'shutdown')
                connection.close()
                cls._worker.join(timeout=1)
                if cls._worker.is_alive():
                    cls._log.warning(f"Manager process {cls._process.pid} did not terminate gracefully.")
                    # TODO Kill the thread using ctypes and pthread.
        except Exception as e:
            cls._log.exception(f'Error terminating event manager: {e}')


class Subprocess:
    """Wrapper for a subprocess with additional metadata and management capabilities."""
    
    def __init__(self, process, process_class, logger, stdout_pipe=None, stderr_pipe=None, 
                 stdout_thread=None, stderr_thread=None):
        """Initialize subprocess wrapper.
        
        :param process: multiprocessing.Process instance
        :param process_class: Class that was used to create the process
        :param logger: Logger instance for this process
        :param stdout_pipe: Tuple of (read_fd, write_fd) for stdout capture
        :param stderr_pipe: Tuple of (read_fd, write_fd) for stderr capture
        :param stdout_thread: Thread handling stdout reading
        :param stderr_thread: Thread handling stderr reading
        """
        self.process = process
        self.process_class = process_class
        self.logger = logger
        self.stdout_pipe = stdout_pipe
        self.stderr_pipe = stderr_pipe
        self.stdout_thread = stdout_thread
        self.stderr_thread = stderr_thread
    
    def is_alive(self):
        """Check if the subprocess is still running."""
        return self.process.is_alive()
    
    def terminate(self):
        """Terminate the subprocess."""
        return self.process.terminate()
    
    def join(self, timeout=None):
        """Wait for the subprocess to terminate."""
        return self.process.join(timeout)
    
    @property
    def pid(self):
        """Get the process ID."""
        return self.process.pid
    
    def cleanup_pipes(self):
        """Clean up pipe file descriptors."""
        if self.stdout_pipe:
            try:
                os.close(self.stdout_pipe[0])
            except:
                pass
        if self.stderr_pipe:
            try:
                os.close(self.stderr_pipe[0])
            except:
                pass


class ProcessManager:
    """Manages execution and termination of subprocesses.
    """

    def __init__(self, manager_address, manager_authkey):
        self._log = getLogger(self.__class__.__name__)
        self._subprocesses = []
        self._manager_address = manager_address
        self._manager_authkey = manager_authkey

        self._log.debug(f'Initializing ProcessManager. Main process PID: {os.getpid()}')
        
        # Register logger method for subprocesses (only once)
        EventManager.register('logger', callable=self.get_subprocess_logger)

    def get_subprocess_logger(self, pid):
        """Get logger for subprocess by PID."""
        return self._subprocesses[pid - 1].logger

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
        
        # Calculate PID for the subprocess (sequential numbering)
        pid = len(self._subprocesses) + 1
        
        # Create logger for this process in the main process
        subprocess_logger = getLogger(process_class.__name__, filter_ansi=filter_ansi, custom_filter=custom_filter)
        
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
                    args=(stdout_read, subprocess_logger, logging.INFO), 
                    daemon=True
                )
                stdout_thread.start()
            
            if capture_stderr:
                stderr_read, stderr_write = os.pipe()
                stderr_pipe = (stderr_read, stderr_write)
                
                stderr_thread = threading.Thread(
                    target=self._pipe_reader, 
                    args=(stderr_read, subprocess_logger, logging.WARNING), 
                    daemon=True
                )
                stderr_thread.start()
        
        p = multiprocessing.Process(target=self._task_wrapper, 
                                    args=(process_class, pid, args, kwargs, stdout_pipe, stderr_pipe, exit_event, halt_event))
        
        # Create Subprocess wrapper
        subprocess = Subprocess(
            process=p,
            process_class=process_class,
            logger=subprocess_logger,
            stdout_pipe=stdout_pipe,
            stderr_pipe=stderr_pipe,
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread
        )
        
        # Store in subprocesses list
        self._subprocesses.append(subprocess)
        p.start()
        
        # Close write ends in parent process
        if stdout_pipe:
            os.close(stdout_pipe[1])
        if stderr_pipe:
            os.close(stderr_pipe[1])
            
        return subprocess

    
    def _task_wrapper(self, process_class, pid, args, kwargs, stdout_pipe, stderr_pipe, exit_event, halt_event):
        """
        The main task executed by each child process.
        """
        # Redirect stdout/stderr if pipes are provided.
        if stdout_pipe:
            os.dup2(stdout_pipe[1], 1)  # Redirect stdout to pipe
            os.close(stdout_pipe[0])    # Close read end in child
            os.close(stdout_pipe[1])    # Close write end after dup2
        
        if stderr_pipe:
            os.dup2(stderr_pipe[1], 2)  # Redirect stderr to pipe
            os.close(stderr_pipe[0])    # Close read end in child
            os.close(stderr_pipe[1])    # Close write end after dup2

        # Connect to the parent process's manager.
        # Register both event_service and logger for client-side access.
        EventManager.register('event_service')
        EventManager.register('logger')
        event_manager = EventManager(address=self._manager_address, authkey=self._manager_authkey)
        try:
            event_manager.connect()
            event_proxy = event_manager.event_service()
            subprocess_logger = event_manager.logger(pid)
        
            # TODO The signal handler is now unused. It may be configurable in the future.
            def signal_handler(signum, frame):
                try:
                    # Try to access exit_event through event_proxy.
                    if 'event_proxy' in locals() and 'subprocess_logger' in locals():
                        if event_proxy.get_exit_event().is_set():
                            return  # Already exiting, return immediately.
                        subprocess_logger.info(f"Child Process {pid} ({process_class.__name__}), PID {os.getpid()}: Received signal {signum}, exiting.")
                        event_proxy.get_exit_event().set()
                except:
                    # Cannot access exit_event, just exit.
                    if 'subprocess_logger' in locals():
                        subprocess_logger.info(f"Child Process {pid} ({process_class.__name__}), PID {os.getpid()}: Received signal {signum}, exiting.")
                sys.exit(0)


            #signal.signal(signal.SIGINT, signal_handler)

            # Ignore SIGINT in child processes - they should exit via exit_event only.
            # This prevents child processes from being killed directly by Ctrl+C.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except Exception as e:
            # Fallback to stderr if connection fails.
            print(f"Child Process {pid} ({process_class.__name__}), PID {os.getpid()}: Failed to connect to manager: {e}", file=sys.stderr)
            sys.exit(1)

        subprocess_logger.debug(f"Child Process {pid} ({process_class.__name__}), PID {os.getpid()}: Starting.")

        try:
            # Call the static hook_up method on the process class.
            process_class.hook_up(event_proxy, subprocess_logger, exit_event, halt_event, *args, **kwargs)
        finally:
            subprocess_logger.debug(f"Child Process {pid} ({process_class.__name__}), PID {os.getpid()}: Exiting.")


    def terminate(self, timeout=5.0):
        """Terminates all subprocesses.
        
        :param timeout: Total time in seconds to wait for graceful shutdown of all processes before killing. If 0, kill immediately.
        """
        self._log.info(f'Terminating child processes... (timeout={timeout}s)')
        
        if not self._subprocesses:
            self._log.debug('No subprocesses to terminate.')
            return
        
        self._log.debug(f'Total subprocesses to terminate: {len(self._subprocesses)}')
        for i, subprocess in enumerate(self._subprocesses):
            if subprocess.is_alive():
                self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}')
            else:
                self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}) already dead.')
        
        if timeout > 0:
            # Wait for graceful termination with shared timeout across all processes.
            import time
            start_time = time.time()
            
            for i, subprocess in enumerate(self._subprocesses):
                if subprocess.is_alive():
                    # Calculate remaining timeout.
                    elapsed = time.time() - start_time
                    remaining_timeout = max(0, timeout - elapsed)
                    
                    self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}: Waiting for graceful termination (timeout={remaining_timeout:.2f}s)...')
                    
                    if remaining_timeout > 0:
                        subprocess.join(timeout=remaining_timeout)
                    
                    if subprocess.is_alive():
                        # If child hasn't terminated, forcibly kill it.
                        self._log.warning(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}: Did not terminate gracefully, sending SIGTERM.')
                        subprocess.terminate()
                        subprocess.join(timeout=1)
                        if subprocess.is_alive():
                            self._log.warning(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}: Still alive after SIGTERM, sending SIGKILL.')
                            os.kill(subprocess.pid, signal.SIGKILL)
                            subprocess.join(timeout=0.5)
                    else:
                        self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}: Terminated gracefully.')
                else:
                    self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}) already dead.')
                
                # Clean up pipes.
                subprocess.cleanup_pipes()
            
            total_elapsed = time.time() - start_time
            self._log.info(f'All child processes terminated in {total_elapsed:.2f}s.')
        else:
            # Kill immediately.
            self._log.debug('Killing all subprocesses immediately (timeout=0).')
            for i, subprocess in enumerate(self._subprocesses):
                if subprocess.is_alive():
                    self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}: Killing immediately.')
                    subprocess.terminate()
                    subprocess.join(timeout=0.5)
                    if subprocess.is_alive():
                        self._log.debug(f'Child Process {i+1} ({subprocess.process_class.__name__}), PID {subprocess.pid}: Still alive, sending SIGKILL.')
                        os.kill(subprocess.pid, signal.SIGKILL)
                
                # Clean up pipes.
                subprocess.cleanup_pipes()
            
            self._log.info('All child processes killed.')