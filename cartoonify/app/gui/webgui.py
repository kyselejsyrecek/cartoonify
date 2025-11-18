import asyncio
import logging
import threading

from app.debugging.logging import getLogger
from .routes import routes
from .app import MainWebGui, SayWebGui
#from app.debugging.tracing import trace


private_host = '127.0.0.1'


class WebGuiProxy:
    """
    Reverse proxy using mitmproxy to route external requests to internal web applications.
    
    Supports HTTP, HTTPS, and WebSocket connections. Handles SSL termination and
    forwards requests to localhost ports based on path mapping.
    """
    
    def __init__(self, listen_host='0.0.0.0', listen_port=8081, 
                 cert_file=None, key_file=None):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.cert_file = cert_file
        self.key_file = key_file
        self._log = getLogger(self.__class__.__name__)
        self._proxy_thread = None
        self._stop_event = threading.Event()
        self._routes = {}
    
    def register_app(self, app_class, host, port):
        """Register an app and its routes for the proxy.
        
        Finds all routes in the routes configuration that use this app_class
        and sets up forwarding to the specified host:port. The path prefix
        (like /say) is stripped before forwarding to the backend server.
        
        Args:
            app_class: The GUI application class (e.g., MainWebGui, SayWebGui).
            host (str): Target host address.
            port (int): Target port number.
        """
        # Find all routes that use this app_class.
        for route_path, route_config in routes.items():
            if route_config['gui_class'] == app_class:
                self._routes[route_path] = {'host': host, 'port': port}
                self._log.debug(f'Registered route: {route_path} -> {host}:{port}')
    
    def start(self):
        if self._proxy_thread and self._proxy_thread.is_alive():
            self._log.warning('WebGuiProxy already running')
            return
        
        if not self._routes:
            self._log.error('No routes registered. Cannot start proxy.')
            return
        
        self._stop_event.clear()
        self._proxy_thread = threading.Thread(target=self._run_proxy, daemon=True)
        self._proxy_thread.start()
        self._log.info(f'WebGuiProxy started on {self.listen_host}:{self.listen_port}')
    
    def stop(self):
        self._stop_event.set()
        if self._proxy_thread:
            self._proxy_thread.join(timeout=5)
        self._log.info('WebGuiProxy stopped')
    
    def _run_proxy(self):
        """Run mitmproxy in dedicated asyncio event loop."""
        try:
            from mitmproxy import options
            from mitmproxy.tools.dump import DumpMaster
            
            # Create new event loop for this thread.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Prevent mitmproxy from injecting its log handler into root logger.
            root_logger = logging.getLogger()
            original_handlers = root_logger.handlers[:]
            
            try:
                opts = options.Options(
                    listen_host=self.listen_host,
                    listen_port=self.listen_port,
                    mode=['regular']
                )
                
                if self.cert_file and self.key_file:
                    opts.certs = [f"{self.cert_file}={self.key_file}"]
                
                # Start event loop so DumpMaster can detect it.
                async def run_proxy():
                    master = DumpMaster(opts, with_termlog=False)
                    
                    # Remove mitmproxy's log handler from root logger to prevent child process errors.
                    for handler in root_logger.handlers[:]:
                        if handler not in original_handlers:
                            root_logger.removeHandler(handler)
                    
                    addon = WebGuiProxyAddon(self._routes)
                    master.addons.add(addon)
                    
                    self._log.info('mitmproxy starting...')
                    await master.run()
                
                loop.run_until_complete(run_proxy())
            finally:
                loop.close()
            
        except ImportError:
            self._log.error('mitmproxy not installed. Install with: pip install mitmproxy')
        except Exception as e:
            self._log.error(f'Error running WebGuiProxy: {e}', exc_info=True)


class WebGuiProxyAddon:
    
    def __init__(self, routes):
        from mitmproxy import http
        
        self._routes = routes
        self._log = getLogger(self.__class__.__name__)
        self._http = http
    
    def request(self, flow):
        path = flow.request.path
        
        matched_route = None
        matched_path = ''
        
        # Longest prefix matching - iterate routes from longest to shortest.
        for route_path in sorted(self._routes.keys(), key=len, reverse=True):
            if path.startswith(route_path):
                # Check that the match is at a proper boundary.
                # For root '/' route, accept everything.
                # For other routes, require '/', '?', or exact match after prefix.
                if route_path == '/':
                    # Root route matches everything (as fallback).
                    matched_route = self._routes[route_path]
                    matched_path = route_path
                    break
                else:
                    # Non-root routes require boundary check.
                    path_after_prefix = path[len(route_path):]
                    if not path_after_prefix or path_after_prefix[0] in ('/', '?'):
                        matched_route = self._routes[route_path]
                        matched_path = route_path
                        break
        
        if matched_route:
            flow.request.host = matched_route['host']
            flow.request.port = matched_route['port']
            flow.request.scheme = 'http'
            
            # Strip the path prefix before forwarding (e.g., /say/foo -> /foo).
            if matched_path != '/':
                flow.request.path = path[len(matched_path):] or '/'
            
            self._log.debug(f"Routing {path} -> {matched_route['host']}:{matched_route['port']}{flow.request.path}")
        else:
            self._log.warning(f'No route found for path: {path}')
            flow.response = self._http.Response.make(
                404,
                b"Not Found",
                {"Content-Type": "text/plain"}
            )


class WebGui:
    """
    WebGui manager
    
    Creates a reverse proxy on external port and manages internal web servers
    as subprocesses via ProcessManager.
    """
    
    def __init__(self, enabled=True):
        self._log = getLogger(self.__class__.__name__)
        self._enabled = enabled
        self._process_manager = None
        self._proxy = None
        self._apps = {}
    
    @property
    def is_enabled(self):
        return self._enabled
    
    def setup(self, process_manager, i18n, cam_only=False, 
              web_host='0.0.0.0', web_port=8081, localhost_first_port=2000,
              start_browser=False, cert_file=None, key_file=None,
              capture_stdout=False, capture_stderr=False, filter_ansi=False):
        """Setup WebGui with reverse proxy and internal web applications.
        
        Args:
            process_manager: ProcessManager instance for spawning subprocess web apps.
            i18n: Internationalization helper.
            cam_only (bool): Camera-only mode flag.
            web_host (str): External proxy host address.
            web_port (int): External proxy port.
            localhost_first_port (int): Base port for internal web applications.
            start_browser (bool): Whether to open browser automatically (applies to MainWebGui only).
            cert_file (str): Path to SSL certificate file.
            key_file (str): Path to SSL private key file.
            capture_stdout (bool): Capture stdout from subprocess web apps.
            capture_stderr (bool): Capture stderr from subprocess web apps.
            filter_ansi (bool): Filter ANSI codes from subprocess output.
        """
        if not self._enabled:
            self._log.info('WebGui is disabled')
            return
        
        self._process_manager = process_manager
        available_port = localhost_first_port
        
        self._log.debug('Starting reverse WebGui proxy')
        self._proxy = WebGuiProxy(
            listen_host=web_host,
            listen_port=web_port,
            cert_file=cert_file,
            key_file=key_file
        )
        
        self._log.info(f"Starting MainWebGui on {private_host}:{available_port}")
        self._apps['main'] = self._process_manager.start_process(
            MainWebGui,
            i18n,
            cam_only,
            private_host,
            available_port,
            start_browser,
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
            filter_ansi=filter_ansi
        )
        self._proxy.register_app(MainWebGui, private_host, available_port)
        available_port += 1
        
        self._log.info(f"Starting SayWebGui on {private_host}:{available_port}")
        self._apps['say'] = self._process_manager.start_process(
            SayWebGui,
            i18n,
            private_host,
            available_port,
            False,  # start_browser is always False for SayWebGui
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
            filter_ansi=filter_ansi
        )
        self._proxy.register_app(SayWebGui, private_host, available_port)
        available_port += 1
        
        self._proxy.start()
        
        self._log.info('WebGui setup complete')
    
    def close(self):
        """Close WebGui and stop proxy. Subprocess termination is handled by ProcessManager."""
        if self._proxy:
            self._proxy.stop()
            self._log.info('WebGui proxy stopped')
