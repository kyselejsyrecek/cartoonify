import logging
import datetime
import sys
import os
import re
from pathlib import Path
from io import StringIO


def strip_ansi_codes(text):
    """Remove ANSI escape sequences and dangerous control characters from text
    
    This prevents terminal control sequences from breaking log file formatting
    and prevents clearing/corrupting the log file content.
    
    Preserves UTF-8 characters including diacritics and special characters.
    Only removes actual ANSI escape sequences and dangerous control characters.
    """
    # ANSI escape sequence patterns:
    # - CSI sequences: ESC[ followed by parameters and final byte (most common)
    # - OSC sequences: ESC] followed by text and terminator
    # - Simple escape sequences: ESC followed by single character
    ansi_csi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')  # CSI sequences like \x1b[2J
    ansi_osc_pattern = re.compile(r'\x1b\][^\x07\x1b]*[\x07\x1b\\]')  # OSC sequences
    ansi_simple_pattern = re.compile(r'\x1b[a-zA-Z]')  # Simple sequences like \x1bE
    
    # Remove ANSI escape sequences
    text = ansi_csi_pattern.sub('', text)
    text = ansi_osc_pattern.sub('', text)
    text = ansi_simple_pattern.sub('', text)
    
    # Remove only dangerous control characters (preserve \n, \t, \r and UTF-8)
    # Remove C0 controls except: \t (0x09), \n (0x0a), \r (0x0d)
    # Remove DEL (0x7f) but preserve all UTF-8 multi-byte sequences (0x80-0xff)
    dangerous_controls = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
    text = dangerous_controls.sub('', text)
    
    return text


class FilteredLogger:
    """Wrapper for standard logger that filters ANSI codes and control characters"""
    
    def __init__(self, logger, filter_ansi=True, custom_filter=None):
        self._logger = logger
        self._filter_ansi = filter_ansi
        self._custom_filter = custom_filter
    
    def _filter_message(self, message):
        """Apply filters to message if enabled"""
        if isinstance(message, str):
            # Apply custom filter first if provided
            if self._custom_filter:
                message = self._custom_filter(message)
            # Apply ANSI filter if enabled
            if self._filter_ansi:
                message = strip_ansi_codes(message)
        return message
    
    def debug(self, message, *args, **kwargs):
        self._logger.debug(self._filter_message(message), *args, **kwargs)
    
    def info(self, message, *args, **kwargs):
        self._logger.info(self._filter_message(message), *args, **kwargs)
    
    def warning(self, message, *args, **kwargs):
        self._logger.warning(self._filter_message(message), *args, **kwargs)
    
    def error(self, message, *args, **kwargs):
        self._logger.error(self._filter_message(message), *args, **kwargs)
    
    def critical(self, message, *args, **kwargs):
        self._logger.critical(self._filter_message(message), *args, **kwargs)
    
    def exception(self, message, *args, **kwargs):
        self._logger.exception(self._filter_message(message), *args, **kwargs)
    
    def log(self, level, message, *args, **kwargs):
        self._logger.log(level, self._filter_message(message), *args, **kwargs)
    
    # Delegate other attributes to the underlying logger
    def __getattr__(self, name):
        return getattr(self._logger, name)


def getLogger(name=None, filter_ansi=True, custom_filter=None):
    """Enhanced getLogger with optional ANSI filtering
    
    :param name: Logger name (same as standard logging.getLogger)
    :param filter_ansi: Whether to filter ANSI escape sequences (default: True)
    :param custom_filter: Custom filter function to apply to messages (default: None)
    :return: FilteredLogger instance
    """
    base_logger = logging.getLogger(name)
    return FilteredLogger(base_logger, filter_ansi=filter_ansi, custom_filter=custom_filter)


class StderrToLogger:
    """Redirect stderr to logger with ERROR level"""
    
    def __init__(self, logger_name='stderr', level=logging.ERROR):
        self.logger = getLogger(logger_name, filter_ansi=True)  # Use our enhanced getLogger
        self.level = level
        self.buffer = StringIO()
    
    def write(self, message):
        # Buffer the message (filtering is handled by FilteredLogger)
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
        self.use_colors = use_colors if use_colors is not None else True
    
    def _get_class_name(self, record):
        """Extract class name from logger name"""
        if '.' in record.name:
            return record.name.split('.')[-1]
        return record.name
    
    def _format_debug_line(self, formatted_time, aligned_severity, aligned_class_name, message):
        """Format complete DEBUG line in gray"""
        bold_severity = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_severity}{self.COLORS['RESET']}{self.COLORS['DEBUG']}"
        bold_class = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_class_name}{self.COLORS['RESET']}{self.COLORS['DEBUG']}"
        return f"{self.COLORS['DEBUG']}[{formatted_time}] {bold_severity} {bold_class}: {message}{self.COLORS['RESET']}"
    
    def _format_other_line(self, formatted_time, aligned_severity, aligned_class_name, message, level):
        """Format INFO, WARNING, ERROR level messages"""
        severity_color = self.COLORS.get(level, '')
        bold_severity = f"{self.COLORS['BOLD']}{severity_color}{aligned_severity}{self.COLORS['RESET']}"
        bold_class = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
        return f"[{formatted_time}] {bold_severity} {bold_class}: {message}"
    
    def format(self, record):
        class_name = self._get_class_name(record)
        formatted_time = self.formatTime(record, '%H:%M:%S.%f')[:-3]
        aligned_severity = f"{record.levelname:>7}"
        aligned_class_name = f"{class_name:>15}"
        message = record.getMessage()
        
        if self.use_colors:
            if record.levelname == 'DEBUG':
                formatted_message = self._format_debug_line(formatted_time, aligned_severity, aligned_class_name, message)
            elif record.levelname == 'CRITICAL':
                formatted_message = f"{self.COLORS['CRITICAL']}[{formatted_time}] {aligned_severity} {aligned_class_name}: {message}{self.COLORS['RESET']}"
            else:
                formatted_message = self._format_other_line(formatted_time, aligned_severity, aligned_class_name, message, record.levelname)
        else:
            formatted_message = f"[{formatted_time}] {aligned_severity} {aligned_class_name}: {message}"
        
        # Handle exceptions
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            if self.use_colors:
                if record.levelname == 'DEBUG':
                    formatted_message += f"\n{self.COLORS['DEBUG']}{exception_text}{self.COLORS['RESET']}"
                elif record.levelname == 'CRITICAL':
                    formatted_message += f"\n{self.COLORS['CRITICAL']}{exception_text}{self.COLORS['RESET']}"
                else:
                    error_severity = f"{self.COLORS['BOLD']}{self.COLORS['ERROR']}   ERROR{self.COLORS['RESET']}"
                    bold_class = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                    exception_lines = exception_text.split('\n')
                    formatted_exception = [f"[{formatted_time}] {error_severity} {bold_class}: {exception_lines[0]}"]
                    spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)
                    formatted_exception.extend(f"{spaces}{line}" for line in exception_lines[1:] if line)
                    formatted_message += '\n' + '\n'.join(formatted_exception)
            else:
                exception_lines = exception_text.split('\n')
                formatted_exception = [f"[{formatted_time}]    ERROR {aligned_class_name}: {exception_lines[0]}"]
                spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)
                formatted_exception.extend(f"{spaces}{line}" for line in exception_lines[1:] if line)
                formatted_message += '\n' + '\n'.join(formatted_exception)
        
        return formatted_message


def setup_logging(logs_dir=None, enable_colors=True, log_level=logging.DEBUG, redirect_stderr=True):
    """Setup centralized logging configuration
    
    :param logs_dir: Directory for log files
    :param enable_colors: Whether to enable colored console output (ignored)
    :param log_level: Logging level
    :param redirect_stderr: Whether to redirect stderr to logging
    :return: Tuple of (log_filename, file_handler, console_handler, stderr_redirector)
    """
    logging_filename = datetime.datetime.now().strftime('%Y%m%d-%H%M.log')
    
    if logs_dir is None:
        logs_dir = Path.cwd() / 'logs'
    else:
        logs_dir = Path(logs_dir)
    
    if not logs_dir.exists():
        logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure file handler with colors
    log_file = logs_dir / logging_filename
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setFormatter(CustomFormatter(use_colors=True))
    
    # Configure root logger
    logging.basicConfig(level=log_level, handlers=[file_handler], force=True)
    
    # Redirect stderr to logging if requested
    stderr_redirector = None
    if redirect_stderr:
        stderr_redirector = StderrToLogger()
        
        # Redirect stderr at file descriptor level for C libraries
        original_stderr_fd = os.dup(sys.stderr.fileno())
        read_fd, write_fd = os.pipe()
        os.dup2(write_fd, sys.stderr.fileno())
        os.close(write_fd)
        sys.stderr = stderr_redirector
        
        # Store file descriptors for cleanup
        stderr_redirector.original_stderr_fd = original_stderr_fd
        stderr_redirector.pipe_read_fd = read_fd
        
        # Start thread to read from pipe and log messages
        import threading
        def pipe_reader():
            try:
                with os.fdopen(read_fd, 'r') as pipe_reader_file:
                    for line in pipe_reader_file:
                        if line.strip():
                            # Filtering is handled by FilteredLogger
                            stderr_redirector.logger.error(line.rstrip('\n'))
            except:
                pass
        
        threading.Thread(target=pipe_reader, daemon=True).start()
    
    return logging_filename, file_handler, None, stderr_redirector


def add_console_logging(enable_colors=True):
    """Add console logging - disabled"""
    return None


def restore_stderr():
    """Restore original stderr if it was redirected"""
    if hasattr(sys.stderr, 'flush') and isinstance(sys.stderr, StderrToLogger):
        sys.stderr.flush()  # Flush any remaining content
        sys.stderr = sys.__stderr__  # Restore original stderr


def setup_debug_console_logging():
    """
    Setup console logging for debug mode.
    ERROR messages go to stderr, all others to stdout.
    """
    # Get root logger
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create stdout handler for non-ERROR messages
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stdout_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    stdout_handler.setFormatter(stdout_formatter)
    
    # Create stderr handler for ERROR messages
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    stderr_handler.setFormatter(stderr_formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.DEBUG)