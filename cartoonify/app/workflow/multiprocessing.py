import logging
import multiprocessing
import os
import signal
import sys
from abc import ABC, abstractmethod

from multiprocessing.managers import BaseManager


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
        self._logger = logging.getLogger(self.__class__.__name__)
        self._subprocesses = []
        self._manager_address = manager_address
        self._manager_authkey = manager_authkey


    def start_process(self, process_class, *args, **kwargs):
        """Start a new process using a ProcessInterface subclass.
        
        :param process_class: Class that inherits from ProcessInterface
        :param args: Additional positional arguments for hook_up
        :param kwargs: Additional keyword arguments for hook_up
        """
        # Validate that the class implements ProcessInterface
        if not issubclass(process_class, ProcessInterface):
            raise ValueError(f"Process class {process_class.__name__} must inherit from ProcessInterface")
        
        # Create logger for this process in the main process
        module_logger = logging.getLogger(process_class.__name__)
        
        p = multiprocessing.Process(target=self._task_wrapper, 
                                    args=(process_class, len(self._subprocesses) + 1, module_logger, args, kwargs))
        self._subprocesses.append([p, process_class])
        p.start()
        return p

    
    def _task_wrapper(self, process_class, id, module_logger, args, kwargs):
        """
        The main task executed by each child process.
        """
        def signal_handler(signum, frame):
            try:
                # Try to access exit_event through event_proxy.
                if 'event_proxy' in locals():
                    if event_proxy.exit_event.is_set():
                        return  # Already exiting, return immediately.
                    print(f"Child Process {id} ({process_class.__name__}): Received signal {signum}, exiting.")
                    event_proxy.exit_event.set()
            except:
                # Cannot access exit_event, just exit.
                print(f"Child Process {id} ({process_class.__name__}): Received signal {signum}, exiting.")
            sys.exit(0)

        # Set up the SIGINT handler for the child process.
        signal.signal(signal.SIGINT, signal_handler)

        print(f"Child Process {id} ({process_class.__name__}): Starting. PID: {os.getpid()}")

        # Connect to the parent process's manager.
        # Register the instance directly (without a callable) for client-side access.
        EventManager.register('event_service')
        event_manager = EventManager(address=self._manager_address, authkey=self._manager_authkey)
        try:
            event_manager.connect()
            event_proxy = event_manager.event_service()
        except Exception as e:
            print(f"Child Process {id} ({process_class.__name__}): Failed to connect to manager: {e}")
            sys.exit(1)

        try:
            # Call the static hook_up method on the process class
            process_class.hook_up(event_proxy, module_logger, *args, **kwargs)
        finally:
            print(f"Child Process {id} ({process_class.__name__}): Exiting.")


    def terminate(self):
        """Terminates all subprocesses.
        """
        self._logger.info('Terminating child processes...')
        # Attempt to gracefully terminate all child processes.
        for p, process_class in self._subprocesses:
            if p.is_alive():
                p.terminate() # Request child to terminate.
                p.join(timeout=1) # Wait for termination with a timeout.
                if p.is_alive():
                    # If child hasn't terminated, forcibly kill it.
                    self._logger.warning(f"Subprocess {p.pid} ({process_class}) did not terminate gracefully, killing.")
                    os.kill(p.pid, signal.SIGKILL)