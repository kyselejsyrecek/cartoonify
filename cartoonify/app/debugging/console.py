"""
Interactive debugging console with proper stderr handling.

This module provides an InteractiveConsole subclass that properly handles
stderr output for interactive Python debugging sessions, ensuring that
console output goes to the original stderr instead of being redirected
to the logging system.
"""

import code
import readline
import atexit
import sys
import signal
from pathlib import Path
from app.debugging.logging import getLogger


class DebugConsole(code.InteractiveConsole):
    """
    Interactive console that properly handles stderr output.
    
    This console ensures that interactive output (banner, prompts, results)
    goes to the original stderr/stdout instead of being redirected to the
    logging system.
    """
    
    def __init__(self):
        super().__init__()
        self._log = getLogger(self.__class__.__name__)
        self._stderr = None
        self._stdout = None
        self._locals = None
        self._history_file = None
        self._save_history_handler = None
        self._original_sigint_handler = None
    
    def setup(self, stderr, stdout, locals_dict):
        """
        Setup the console with stderr/stdout and local variables.
        
        :param stderr: Original stderr stream for console output
        :param stdout: Original stdout stream for console output  
        :param locals_dict: Local variables to make available in console
        """
        self._stderr = stderr
        self._stdout = stdout
        self._locals = locals_dict
        self.locals.update(locals_dict)
    
    def write(self, data):
        """
        Override write method to send output to original stderr.
        
        This ensures that console banner, prompts, and interactive output
        go to the original console instead of being logged.
        """
        if self._stderr:
            self._stderr.write(data)
            self._stderr.flush()
        else:
            # Fallback to current stderr if original not available
            sys.stderr.write(data)
            sys.stderr.flush()
    
    def _save_history(self):
        """Internal method to save console history."""
        if self._history_file:
            try:
                readline.write_history_file(str(self._history_file))
            except Exception:
                pass  # Ignore errors saving history.
    
    def setup_console_history(self):
        """Setup interactive console history support."""
        # Path to console history file.
        settings_dir = Path(__file__).parent.parent.parent / '.settings'
        settings_dir.mkdir(exist_ok=True)
        self._history_file = settings_dir / 'console_history'
        
        # Load existing history if available.
        if self._history_file.exists():
            try:
                readline.read_history_file(str(self._history_file))
            except Exception:
                pass  # Ignore errors loading history.
        
        # Setup history saving on exit.
        self._save_history_handler = self._save_history
        atexit.register(self._save_history_handler)
        
        # Set maximum history length.
        readline.set_history_length(1000)
        
        return self._history_file
    
    def cleanup_console_history(self):
        """Cleanup console history and restore original readline state."""
        # Save current history before cleanup
        self._save_history()
        
        # Unregister the atexit handler
        if self._save_history_handler:
            try:
                atexit.unregister(self._save_history_handler)
            except ValueError:
                pass  # Handler wasn't registered or already removed
            self._save_history_handler = None
        
        # Clear readline history to restore original state
        try:
            readline.clear_history()
        except Exception:
            pass  # Ignore errors clearing history
        
        self._history_file = None
    
    def start(self):
        """
        Start the interactive console session.
        
        This method sets up console history, starts the interactive session,
        and handles cleanup when the session ends.
        """
        # Setup console history support
        history_file = self.setup_console_history()
        self._log.info(f'Console history will be saved to: {history_file}')
        
        self._log.info('Starting interactive Python console for debugging...')
        
        # Temporarily redirect stdout as well for complete console experience
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        # Save current SIGINT handler and restore default for console
        self._original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_DFL)
        
        console_exited_normally = False
        
        try:
            # Redirect both stdout and stderr to original streams for interaction
            if self._stdout:
                sys.stdout = self._stdout
            if self._stderr:
                sys.stderr = self._stderr
            
            # Start interactive session
            self.interact(banner="Interactive debugging console started.\nType 'exit()' or press Ctrl+D to quit.\nPress Ctrl+C to interrupt current operation.")
            console_exited_normally = True
            
        # FIXME Ctrl+C and Ctrl+D interrupts not working properly.
        except SystemExit:
            console_exited_normally = True
        except EOFError:
            # Handle Ctrl+D explicitly
            self._log.info('Console session ended with Ctrl+D.')
            console_exited_normally = True
        except KeyboardInterrupt:
            # Handle Ctrl+C - just log it, don't exit the application
            self._log.info('Console operation interrupted with Ctrl+C.')
            console_exited_normally = False
        finally:
            # Restore original SIGINT handler
            if self._original_sigint_handler is not None:
                signal.signal(signal.SIGINT, self._original_sigint_handler)
                self._original_sigint_handler = None
            
            # Restore redirected streams
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Cleanup console history and restore original readline state
            self.cleanup_console_history()
        
        if console_exited_normally:
            self._log.info('Interactive console session ended normally - shutting down.')
        else:
            # Console was interrupted, offer to restart
            if self._stderr:
                self._stderr.write("\nConsole interrupted. Restart? (y/n): ")
                self._stderr.flush()
                try:
                    response = input().strip().lower()
                    if response in ('y', 'yes', ''):
                        return self.start()  # Restart console
                except (EOFError, KeyboardInterrupt):
                    pass
            
            self._log.info('Console session aborted by user.')
