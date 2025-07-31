import logging
import datetime
import sys
import os
from pathlib import Path
from io import StringIO


class StderrToLogger:
    """Redirect stderr to logger with ERROR level"""
    
    def __init__(self, logger_name='stderr', level=logging.ERROR):
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.buffer = StringIO()
    
    def write(self, message):
        # Buffer the message
        self.buffer.write(message)
        
        # If we have a complete line (ends with newline), log it
        if message.endswith('\n'):
            content = self.buffer.getvalue().rstrip('\n')
            if content.strip():  # Only log non-empty messages
                self.logger.log(self.level, content)
            self.buffer = StringIO()  # Reset buffer
    
    def flush(self):
        # Flush any remaining content in buffer
        content = self.buffer.getvalue().rstrip('\n')
        if content.strip():
            self.logger.log(self.level, content)
        self.buffer = StringIO()
    
    def isatty(self):
        return False


class CustomFormatter(logging.Formatter):
    """Custom logging formatter with colors and alignment"""
    
    # ANSI color codes for terminal output
    COLORS = {
        'DEBUG': '\033[90m',      # Gray (dark white) - entire line
        'INFO': '\033[37m',       # White
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[41;93m', # Yellow text on red background
        'RESET': '\033[0m',       # Reset to default
        'BOLD': '\033[1m',        # Bold text
        'WHITE_BOLD': '\033[1;97m' # Bold bright white
    }
    
    def __init__(self, use_colors=None):
        super().__init__()
        # Auto-detect if we should use colors
        if use_colors is None:
            self.use_colors = self._should_use_colors()
        else:
            self.use_colors = use_colors
    
    def _should_use_colors(self):
        """Check if terminal supports colors"""
        # Check if output is a terminal and supports colors
        return (
            hasattr(sys.stderr, 'isatty') and sys.stderr.isatty() and
            os.environ.get('TERM', '').lower() not in ('', 'dumb') and
            os.environ.get('NO_COLOR', '').lower() not in ('1', 'true', 'yes')
        )
    
    def format(self, record):
        # Extract just the class name from logger name (e.g., picamera2.picamera2 -> picamera2)
        logger_name = record.name
        if '.' in logger_name:
            # Take the last part after the last dot
            class_name = logger_name.split('.')[-1]
        else:
            class_name = logger_name
        
        # Create aligned format with time in brackets, severity, and right-aligned class name
        formatted_time = self.formatTime(record, '%H:%M:%S.%f')[:-3]  # Remove last 3 digits for milliseconds
        # Right-align severity to 7 characters and class name to 15 characters
        aligned_severity = f"{record.levelname:>7}"
        aligned_class_name = f"{class_name:>15}"
        
        # Apply colors if terminal supports them
        if self.use_colors:
            if record.levelname == 'DEBUG':
                # Entire DEBUG line is gray with bold severity and bold gray class name
                bold_debug_severity = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_severity}{self.COLORS['RESET']}"
                bold_gray_class_name = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_class_name}{self.COLORS['RESET']}"
                formatted_message = f"{self.COLORS['DEBUG']}[{formatted_time}] {bold_debug_severity} {bold_gray_class_name}: {record.getMessage()}{self.COLORS['RESET']}"
            elif record.levelname == 'CRITICAL':
                # Entire CRITICAL line with background color
                formatted_message = f"{self.COLORS['CRITICAL']}[{formatted_time}] {aligned_severity} {aligned_class_name}: {record.getMessage()}{self.COLORS['RESET']}"
            else:
                # Other levels: bold severity + bold white class name
                severity_color = self.COLORS.get(record.levelname, '')
                bold_severity = f"{self.COLORS['BOLD']}{severity_color}{aligned_severity}{self.COLORS['RESET']}"
                bold_class_name = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                formatted_message = f"[{formatted_time}] {bold_severity} {bold_class_name}: {record.getMessage()}"
        else:
            formatted_message = f"[{formatted_time}] {aligned_severity} {aligned_class_name}: {record.getMessage()}"
        
        # Handle exceptions
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            if self.use_colors:
                if record.levelname == 'DEBUG':
                    # Gray exceptions for DEBUG
                    formatted_message += f"\n{self.COLORS['DEBUG']}{exception_text}{self.COLORS['RESET']}"
                elif record.levelname == 'CRITICAL':
                    # Critical background for CRITICAL exceptions
                    formatted_message += f"\n{self.COLORS['CRITICAL']}{exception_text}{self.COLORS['RESET']}"
                else:
                    # Format exceptions with ERROR severity and normal white text
                    error_severity = f"{self.COLORS['BOLD']}{self.COLORS['ERROR']}   ERROR{self.COLORS['RESET']}"
                    bold_class_name = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                    # Split exception text into lines and format each with ERROR prefix
                    exception_lines = exception_text.split('\n')
                    formatted_exception = []
                    for i, line in enumerate(exception_lines):
                        if i == 0:
                            # First line gets full ERROR formatting
                            formatted_exception.append(f"[{formatted_time}] {error_severity} {bold_class_name}: {line}")
                        else:
                            # Subsequent lines are just indented with spaces to align with message
                            spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)  # time + severity + space + class + ": "
                            formatted_exception.append(f"{spaces}{line}")
                    formatted_message += '\n' + '\n'.join(formatted_exception)
            else:
                # Plain text exceptions with ERROR prefix
                exception_lines = exception_text.split('\n')
                formatted_exception = []
                for i, line in enumerate(exception_lines):
                    if i == 0:
                        formatted_exception.append(f"[{formatted_time}]    ERROR {aligned_class_name}: {line}")
                    else:
                        spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)
                        formatted_exception.append(f"{spaces}{line}")
                formatted_message += '\n' + '\n'.join(formatted_exception)
        
        return formatted_message


def setup_logging(logs_dir=None, enable_colors=True, log_level=logging.DEBUG, redirect_stderr=True):
    """Setup centralized logging configuration - ONLY FILE OUTPUT WITH COLORS
    
    :param logs_dir: Directory for log files (defaults to current directory / 'logs')
    :param enable_colors: Whether to enable colored console output (IGNORED - no console output)
    :param log_level: Logging level (default: DEBUG)
    :param redirect_stderr: Whether to redirect stderr to logging (default: True)
    :return: Tuple of (log_filename, file_handler, console_handler, stderr_redirector)
    """
    # Generate log filename
    logging_filename = datetime.datetime.now().strftime('%Y%m%d-%H%M.log')
    
    # Set up logs directory
    if logs_dir is None:
        logs_dir = Path.cwd() / 'logs'
    else:
        logs_dir = Path(logs_dir)
    
    if not logs_dir.exists():
        logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure file handler WITH COLORS (this is what you want)
    log_file = logs_dir / logging_filename
    file_handler = logging.FileHandler(str(log_file))
    file_formatter = CustomFormatter(use_colors=True)  # COLORS IN FILE!
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger with ONLY file handler - NO CONSOLE
    logging.basicConfig(
        level=log_level,
        handlers=[file_handler],  # ONLY file handler
        force=True  # Override any existing configuration
    )
    
    # Redirect stderr to logging if requested
    stderr_redirector = None
    if redirect_stderr:
        # Create StderrToLogger for Python-level stderr
        stderr_redirector = StderrToLogger()
        
        # Also redirect stderr at file descriptor level for C libraries like libcamera
        # Save original stderr file descriptor
        original_stderr_fd = os.dup(sys.stderr.fileno())
        
        # Create a pipe for capturing low-level stderr
        read_fd, write_fd = os.pipe()
        
        # Redirect stderr file descriptor to write end of pipe
        os.dup2(write_fd, sys.stderr.fileno())
        os.close(write_fd)
        
        # Set up Python-level stderr redirect
        sys.stderr = stderr_redirector
        
        # Store original stderr fd in redirector for cleanup
        stderr_redirector.original_stderr_fd = original_stderr_fd
        stderr_redirector.pipe_read_fd = read_fd
        
        # Start thread to read from pipe and log messages
        import threading
        def pipe_reader():
            try:
                with os.fdopen(read_fd, 'r') as pipe_reader_file:
                    for line in pipe_reader_file:
                        if line.strip():
                            stderr_redirector.logger.error(line.rstrip('\n'))
            except:
                pass  # Ignore errors in pipe reader
        
        pipe_thread = threading.Thread(target=pipe_reader, daemon=True)
        pipe_thread.start()
        stderr_redirector.pipe_thread = pipe_thread
    
    return logging_filename, file_handler, None, stderr_redirector


def add_console_logging(enable_colors=True):
    """Add console logging to existing configuration - DISABLED
    
    :param enable_colors: Whether to enable colored console output (IGNORED)
    :return: Console handler (always None)
    """
    # DO NOT ADD CONSOLE LOGGING - ALL OUTPUT GOES ONLY TO FILE
    return None


def restore_stderr():
    """Restore original stderr if it was redirected"""
    if hasattr(sys.stderr, 'flush') and isinstance(sys.stderr, StderrToLogger):
        sys.stderr.flush()  # Flush any remaining content
        sys.stderr = sys.__stderr__  # Restore original stderr