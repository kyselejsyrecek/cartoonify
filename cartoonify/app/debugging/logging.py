import logging
import datetime
import sys
import os
import re
from pathlib import Path
from io import StringIO


def strip_ansi_codes(text):
    """Remove ANSI escape sequences and dangerous control characters from text"""
    if not isinstance(text, str):
        return text
    
    # ANSI escape sequence patterns
    ansi_csi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    ansi_osc_pattern = re.compile(r'\x1b\][^\x07\x1b]*[\x07\x1b\\]')
    ansi_simple_pattern = re.compile(r'\x1b[a-zA-Z]')
    
    # Remove ANSI escape sequences
    text = ansi_csi_pattern.sub('', text)
    text = ansi_osc_pattern.sub('', text)
    text = ansi_simple_pattern.sub('', text)
    
    # Remove dangerous control characters (preserve \n, \t, \r)
    dangerous_controls = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
    text = dangerous_controls.sub('', text)
    
    return text


class FilteredLogger:
    """Wrapper for standard logger that filters ANSI codes"""
    
    def __init__(self, logger, filter_ansi=True, custom_filter=None):
        self._logger = logger
        self._filter_ansi = filter_ansi
        self._custom_filter = custom_filter
    
    def _filter_message(self, message):
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
    
    def __getattr__(self, name):
        return getattr(self._logger, name)


class StderrRedirector:
    """Redirect stderr to logger"""
    
    def __init__(self, logger_name='STDERR'):
        self.logger = logging.getLogger(logger_name)
        self.buffer = StringIO()
        self.original_stderr = sys.stderr
    
    def write(self, message):
        self.buffer.write(message)
        if message.endswith('\n'):
            content = self.buffer.getvalue().rstrip('\n')
            if content.strip():
                # Messages written to stderr are often just informative.
                self.logger.warning(f"STDERR: {content}")
            self.buffer = StringIO()
    
    def flush(self):
        content = self.buffer.getvalue().rstrip('\n')
        if content.strip():
            # Messages written to stderr are often just informative.
            self.logger.warning(f"STDERR: {content}")
        self.buffer = StringIO()
    
    def restore(self):
        sys.stderr = self.original_stderr


class CustomFormatter(logging.Formatter):
    """Custom logging formatter with optional colors"""
    
    COLORS = {
        'DEBUG': '\033[90m',      # Gray
        'INFO': '\033[37m',       # White
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[41;93m', # Yellow on red background
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'WHITE_BOLD': '\033[1;97m'
    }
    
    def __init__(self, use_colors=False):
        super().__init__()
        self.use_colors = use_colors
    
    def _get_class_name(self, record):
        if '.' in record.name:
            return record.name.split('.')[-1]
        return record.name
    
    def _should_promote_to_error(self, message):
        """Check if message contains keywords that should promote it to ERROR level."""
        if not isinstance(message, str):
            return False
        
        # Keywords that indicate error conditions
        error_keywords = ['error', 'fail', 'failure', 'exception']
        message_lower = message.lower()
        
        return any(keyword in message_lower for keyword in error_keywords)
    
    def format(self, record):
        class_name = self._get_class_name(record)
        formatted_time = self.formatTime(record, '%H:%M:%S.%f')[:-3]
        message = record.getMessage()
        
        # Check if message should be promoted to ERROR level
        original_levelname = record.levelname
        if (record.levelno < logging.ERROR and 
            original_levelname in ['INFO', 'WARNING', 'DEBUG'] and 
            self._should_promote_to_error(message)):
            # Temporarily change the level for formatting
            record.levelname = 'ERROR'
            record.levelno = logging.ERROR
        
        aligned_severity = f"{record.levelname:>7}"
        aligned_class_name = f"{class_name:>15}"
        
        if self.use_colors:
            if record.levelname == 'DEBUG':
                bold_severity = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_severity}{self.COLORS['RESET']}{self.COLORS['DEBUG']}"
                bold_class = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_class_name}{self.COLORS['RESET']}{self.COLORS['DEBUG']}"
                formatted_message = f"{self.COLORS['DEBUG']}[{formatted_time}] {bold_severity} {bold_class}: {message}{self.COLORS['RESET']}"
            elif record.levelname == 'CRITICAL':
                formatted_message = f"{self.COLORS['CRITICAL']}[{formatted_time}] {aligned_severity} {aligned_class_name}: {message}{self.COLORS['RESET']}"
            else:
                severity_color = self.COLORS.get(record.levelname, '')
                bold_severity = f"{self.COLORS['BOLD']}{severity_color}{aligned_severity}{self.COLORS['RESET']}"
                bold_class = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                formatted_message = f"[{formatted_time}] {bold_severity} {bold_class}: {message}"
        else:
            formatted_message = f"[{formatted_time}] {aligned_severity} {aligned_class_name}: {message}"
        
        # Handle exceptions
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            if self.use_colors and record.levelname != 'DEBUG':
                error_severity = f"{self.COLORS['BOLD']}{self.COLORS['ERROR']}   ERROR{self.COLORS['RESET']}"
                bold_class = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                exception_lines = exception_text.split('\n')
                formatted_exception = [f"[{formatted_time}] {error_severity} {bold_class}: {exception_lines[0]}"]
                spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)
                formatted_exception.extend(f"{spaces}{line}" for line in exception_lines[1:] if line)
                formatted_message += '\n' + '\n'.join(formatted_exception)
            else:
                formatted_message += f"\n{exception_text}"
        
        # Restore original level if it was temporarily changed
        if 'original_levelname' in locals() and record.levelname != original_levelname:
            record.levelname = original_levelname
            if original_levelname == 'DEBUG':
                record.levelno = logging.DEBUG
            elif original_levelname == 'INFO':
                record.levelno = logging.INFO
            elif original_levelname == 'WARNING':
                record.levelno = logging.WARNING
        
        return formatted_message


def _create_file_handler(logs_dir, log_level, use_colors=True):
    """Create file handler for logging"""
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    log_filename = logs_dir / f"{timestamp}.log"
    
    file_handler = logging.FileHandler(str(log_filename))
    file_handler.setLevel(log_level)
    file_handler.setFormatter(CustomFormatter(use_colors=use_colors))
    
    return file_handler


def _create_console_handlers(log_level, use_colors):
    """Create console handlers for debug mode"""
    # stdout handler for non-ERROR messages
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stdout_handler.setFormatter(CustomFormatter(use_colors=use_colors))
    
    # stderr handler for ERROR messages
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(CustomFormatter(use_colors=use_colors))
    
    return stdout_handler, stderr_handler


def setup_file_logging(logs_dir, log_level=logging.DEBUG, redirect_stderr=True, use_colors=True):
    """Setup file-only logging (normal mode)"""
    root_logger = logging.getLogger()
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add file handler
    file_handler = _create_file_handler(logs_dir, log_level, use_colors)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(log_level)
    
    # Setup stderr redirection with proper file descriptor redirection
    stderr_redirector = None
    if redirect_stderr:
        stderr_redirector = StderrRedirector()
        
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
                            # Messages written to stderr are often just informative.
                            stderr_redirector.logger.warning(line.rstrip('\n'))
            except:
                pass
        
        threading.Thread(target=pipe_reader, daemon=True).start()
    
    return stderr_redirector


def setup_debug_logging(log_level=logging.DEBUG, use_colors=True):
    """Setup console-only logging (debug mode)"""
    root_logger = logging.getLogger()
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add console handlers
    stdout_handler, stderr_handler = _create_console_handlers(log_level, use_colors)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(log_level)
    
    # In debug mode, also redirect stderr to get proper formatting
    stderr_redirector = StderrRedirector()
    sys.stderr = stderr_redirector
    
    return stderr_redirector


def getLogger(name=None, filter_ansi=False, custom_filter=None):
    """Get logger with optional ANSI filtering and custom message filtering"""
    base_logger = logging.getLogger(name)
    
    if filter_ansi or custom_filter:
        return FilteredLogger(base_logger, filter_ansi=filter_ansi, custom_filter=custom_filter)
    else:
        return base_logger