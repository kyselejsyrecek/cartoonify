import logging
import multiprocessing
import os
import signal
import sys

from multiprocessing.managers import BaseManager


# Global event for signaling processes to exit
exit_event = multiprocessing.Event()
halt_event = multiprocessing.Event()


# Class whose methods will be called remotely
#class EventService:
#    def handle_event(self, message, process_id):
#        """
#        This method is called in the parent process, but is triggered by a child process.
#        """
#        print(f"Parent Process: Received remote message '{message}' from process {process_id}")
#        # Implement any logic here that should be executed based on the child's message.


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


    def start_process(self, task, *args, **kwargs):
        p = multiprocessing.Process(target=self._task_wrapper, 
                                    args=(task, len(self._subprocesses) + 1, args, kwargs))
        self._subprocesses.append([p, task])
        p.start()
        return p

    
    def _task_wrapper(self, task, id, args, kwargs):
        """
        The main task executed by each child process.
        """
        def signal_handler(signum, frame):
            print(f"Child Process {id} ({task}): Received signal {signum}, exiting.")
            exit_event.set() # Set the event to signal the main loop to exit
            sys.exit(0)

        # Set up the SIGINT handler for the child process
        signal.signal(signal.SIGINT, signal_handler)

        print(f"Child Process {id} ({task}): Starting. PID: {os.getpid()}")

        # Connect to the parent process's manager
        # Register the instance directly (without a callable) for client-side access
        EventManager.register('event_service')
        event_manager = EventManager(address=self._manager_address, authkey=self._manager_authkey)
        try:
            event_manager.connect()
            event_proxy = event_manager.event_service()
        except Exception as e:
            print(f"Child Process {id} ({task}): Failed to connect to manager: {e}")
            sys.exit(1)

        try:
            task(event_proxy, *args, **kwargs)
        finally:
            print(f"Child Process {id} ({task}): Exiting.")


    def terminate(self):
        """Terminates all subprocesses.
        """
        self._logger.info('Terminating child processes...')
        # Attempt to gracefully terminate all child processes
        for p, task in self._subprocesses:
            if p.is_alive():
                p.terminate() # Request child to terminate
                p.join(timeout=1) # Wait for termination with a timeout
                if p.is_alive():
                    # If child hasn't terminated, forcibly kill it
                    self._logger.warning(f"Subprocess {p.pid} ({task}) did not terminate gracefully, killing.")
                    os.kill(p.pid, signal.SIGKILL)