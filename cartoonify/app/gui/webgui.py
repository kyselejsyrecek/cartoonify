"""
WebGui Manager

Manages REMI web applications running on separate subdomains or ports.
Each application runs in its own subprocess via ProcessManager.

Subdomain Mode:
- MainWebGui runs on hostname:80 (e.g., raspberrypi.local:80)
- SayWebGui runs on say.hostname:80 (e.g., say.raspberrypi.local:80)

Port Mode (fallback when subdomains are unavailable):
- MainWebGui runs on hostname:80 (or specified port)
- SayWebGui runs on hostname:2000 (first subordinate port from first_subordinate_port)
"""

import socket
import ipaddress

from app.debugging.logging import getLogger
from .app import MainWebGui, SayWebGui


def get_system_hostname():
    """Get the system hostname.
    
    Returns:
        str: System hostname (e.g., 'raspberrypi').
    """
    return socket.gethostname()


def is_subdomain_capable(hostname):
    """Check if hostname supports subdomains.
    
    IP addresses cannot have subdomains. Hostnames can.
    
    Args:
        hostname (str): Hostname or IP address to check.
        
    Returns:
        bool: True if hostname supports subdomains, False otherwise.
    """
    # Check if it's an IP address.
    try:
        ipaddress.ip_address(hostname)
        return False  # IP addresses don't support subdomains.
    except ValueError:
        pass
    
    # Hostname supports subdomains.
    return True


class WebGui:
    """
    WebGui manager
    
    Manages REMI web applications as subprocesses. Applications are hosted either:
    1. On subdomains (when hostname supports it): main.hostname:80, say.hostname:80
    2. On separate ports (fallback): hostname:80, hostname:2000
    """
    
    def __init__(self, enabled=True):
        self._log = getLogger(self.__class__.__name__)
        self._enabled = enabled
        self._process_manager = None
        self._apps = {}
    
    @property
    def is_enabled(self):
        return self._enabled
    
    def setup(self, process_manager, i18n, cam_only=False, 
              host='0.0.0.0', main_port=80, first_subordinate_port=2000,
              start_browser=False, cert_file=None, key_file=None,
              capture_stdout=False, capture_stderr=False, filter_ansi=False):
        """Setup WebGui with direct application hosting.
        
        Args:
            process_manager: ProcessManager instance for spawning subprocess web apps.
            i18n: Internationalization helper.
            cam_only (bool): Camera-only mode flag.
            host (str): Hostname or IP address to bind to.
            main_port (int): Port for main web application (MainWebGui, default: 80).
            first_subordinate_port (int): Base port for subordinate web applications (like SayWebGui) when subdomains unavailable.
            start_browser (bool): Whether to open browser automatically (applies to MainWebGui only).
            cert_file (str): Path to TLS certificate file for HTTPS.
            key_file (str): Path to TLS private key file for HTTPS.
            capture_stdout (bool): Capture stdout from subprocess web apps.
            capture_stderr (bool): Capture stderr from subprocess web apps.
            filter_ansi (bool): Filter ANSI codes from subprocess output.
        """
        if not self._enabled:
            self._log.info('WebGui is disabled')
            return False
        
        self._process_manager = process_manager
        
        # Use system hostname if not explicitly specified.
        if host is None:
            host = get_system_hostname()
        
        use_subdomains = is_subdomain_capable(host)
        
        main_host = host
        if use_subdomains:
            self._log.debug(f'Using subdomain mode with hostname: {host}')
            say_host = f'say.{host}'
            say_port = main_port
        else:
            self._log.info(f'Host "{host}" does not support subdomains - using port mode')
            say_host = host
            say_port = first_subordinate_port
        
        # Start MainWebGui.
        self._log.info(f'Starting MainWebGui on {main_host}:{main_port}')
        self._apps['main'] = self._process_manager.start_process(
            MainWebGui,
            i18n,
            cam_only,
            main_host,
            main_port,
            start_browser,
            cert_file,
            key_file,
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
            filter_ansi=filter_ansi
        )
        if not start_browser:
            print(f'Main WebGUI running on http://{main_host}:{main_port}.')
        
        # Start SayWebGui.
        self._log.info(f'Starting SayWebGui on {say_host}:{say_port}')
        self._apps['say'] = self._process_manager.start_process(
            SayWebGui,
            i18n,
            say_host,
            say_port,
            False,  # start_browser always False for SayWebGui.
            cert_file,
            key_file,
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
            filter_ansi=filter_ansi
        )
        if not start_browser:
            print(f'Say WebGUI running on http://{say_host}:{say_port}.')

        return True
