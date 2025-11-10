"""
REMI Multi-Path Router Extension

This module extends REMI framework to support multiple URL paths with different App instances.

REMI Architecture Analysis:
============================
1. ThreadedHTTPServer receives HTTP requests.
2. Server's do_GET() handles initial HTTP GET for root HTML document.
3. For WebSocket connections (/), REMI creates ONE App instance per client.
4. App.__init__(*userdata) is called, then App.main(*userdata) is called.
5. The returned widget from main() becomes the root widget for that client.
6. App.path attribute is NOT set in __init__, it's set by server AFTER instance creation.

Key Challenge:
- REMI's design: ONE App class per server, ONE instance per WebSocket client.
- Goal: Different App classes/instances based on URL path (/main vs /say).
- Problem: Path is not available during __init__ - it's set later by server.

Solution Strategy:
==================
We use multi-layered approach:

1. **Monkey-patch REMI Server**: Intercept do_GET() to store path in thread-local storage
   BEFORE App instance is created.

2. **RouterApp as Proxy**: Single App class that REMI instantiates. It reads the path
   from thread-local storage and creates the appropriate target App (MainGui/SayGui).

3. **Attribute Delegation**: RouterApp proxies all method calls and attribute access
   to the target App, making it transparent.

4. **Session Management**: Each WebSocket client gets its own RouterApp instance,
   which maintains its own target App instance.

This approach:
- Minimal REMI patching (only do_GET for path extraction).
- Works within REMI's architecture.
- Supports multiple concurrent sessions on different paths.
- Maintains full REMI functionality (events, updates, etc.).
- Preserves userdata passing for ProcessInterface integration.
"""

import logging
import remi.gui as gui
from remi import App, start as remi_start
from remi.server import runtimeInstances, Server
import threading
import sys


log = logging.getLogger('remi.router')


# Thread-local storage for passing request context from server to App.__init__().
_thread_local = threading.local()


# Store original Server.do_GET for restoration if needed.
_original_server_do_GET = None


def _patched_do_GET(self):
    """Patched Server.do_GET() that stores the requested path in thread-local storage.
    
    This allows RouterApp.__init__() to access the path BEFORE REMI creates the App instance.
    
    The path is stored in _thread_local.current_path and read by RouterApp.__init__().
    """
    # Extract the path from the request.
    # self.path contains the full request path (e.g., "/say", "/say?param=value").
    path = self.path.split('?')[0]  # Remove query string.
    
    # Store in thread-local storage.
    _thread_local.current_path = path
    
    log.debug(f'Server.do_GET: Stored path={path} in thread-local storage')
    
    # Call original do_GET().
    return _original_server_do_GET(self)


def _patch_remi_server():
    """Monkey-patch REMI Server to intercept path before App creation.
    
    This patches Server.do_GET() to store the requested path in thread-local storage.
    The path can then be accessed by RouterApp.__init__().
    """
    global _original_server_do_GET
    
    if _original_server_do_GET is not None:
        # Already patched.
        log.debug('REMI Server already patched')
        return
    
    # Store original method.
    _original_server_do_GET = Server.do_GET
    
    # Replace with patched version.
    Server.do_GET = _patched_do_GET
    
    log.info('REMI Server patched for multi-path routing')


def _unpatch_remi_server():
    """Restore original REMI Server.do_GET() method.
    
    This is provided for cleanup, though typically not needed.
    """
    global _original_server_do_GET
    
    if _original_server_do_GET is None:
        # Not patched.
        return
    
    # Restore original.
    Server.do_GET = _original_server_do_GET
    _original_server_do_GET = None
    
    log.info('REMI Server unpatch completed')


class RouterApp(App):
    """
    Router App that delegates to different target Apps based on URL path.
    
    This is the ONLY App class registered with REMI server.
    It maintains separate target App instances for different URL paths and
    proxies all REMI lifecycle methods to the active target.
    
    Architecture:
    - REMI creates ONE RouterApp instance per WebSocket client.
    - RouterApp determines the URL path from the initial request.
    - RouterApp creates the appropriate target App (MainGui, SayGui, etc.).
    - RouterApp delegates all method calls to the target App.
    - Each WebSocket client can access different paths (e.g., /main and /say).
    """
    
    # Class-level route registry.
    # Format: {'/path': TargetAppClass}
    _routes = {}
    
    # Class-level lock for thread-safe route access.
    _routes_lock = threading.RLock()
    
    # Default path when no specific path is requested.
    _default_path = '/'
    
    @classmethod
    def register_routes(cls, routes, default_path='/'):
        """Register URL routes with their corresponding App classes.
        
        Args:
            routes (dict): Mapping of URL paths to App classes.
                Example: {'/': MainGui, '/say': SayGui}
            default_path (str): Default path when none specified.
        """
        with cls._routes_lock:
            cls._routes = routes.copy()
            cls._default_path = default_path
            log.info(f'Registered routes: {list(routes.keys())}, default: {default_path}')
    
    def __init__(self, *userdata, **kwargs):
        """Initialize RouterApp.
        
        REMI calls this with userdata tuple passed to start().
        We determine the target App class, create it, and proxy to it.
        
        CRITICAL: We do NOT call App.__init__() ourselves because the target App
        will do that. We just set up proxying.
        
        Args:
            *userdata: User data tuple from start() function.
            **kwargs: Additional keyword arguments (from REMI internals).
        """
        # Store userdata for passing to target App.
        self._userdata = userdata
        self._kwargs = kwargs
        
        # Determine the requested path.
        self._requested_path = self._determine_path()
        
        # Select target App class based on path.
        with self._routes_lock:
            target_class = self._routes.get(self._requested_path)
            
            # Try prefix matching if exact match fails.
            if target_class is None and self._requested_path != '/':
                for route_path in sorted(self._routes.keys(), key=len, reverse=True):
                    if self._requested_path.startswith(route_path):
                        target_class = self._routes[route_path]
                        break
            
            # Fallback to default path.
            if target_class is None:
                log.warning(f'No route found for {self._requested_path}, using default {self._default_path}')
                self._requested_path = self._default_path
                target_class = self._routes.get(self._default_path)
            
            if target_class is None:
                raise ValueError(f'No App class registered for path: {self._requested_path}')
        
        log.info(f'RouterApp routing {self._requested_path} -> {target_class.__name__}')
        
        # Create target App instance.
        # CRITICAL: The target App's __init__ will call App.__init__, which sets up
        # all REMI internals (identifier, runtimeInstances registration, etc.).
        try:
            self._target_app = target_class(*userdata, **kwargs)
        except Exception as e:
            log.exception(f'Failed to create target App {target_class.__name__}: {e}')
            raise
        
        # DO NOT call App.__init__() - that would duplicate initialization.
        # Instead, we become a transparent proxy to the target App.
        
        # Store essential attributes for our own use.
        self._target_class = target_class
        self._is_initialized = True
        
        log.debug(f'RouterApp created with target {target_class.__name__}, identifier={self._target_app.identifier}')
    
    def _determine_path(self):
        """Determine the requested URL path.
        
        Path is stored in thread-local storage by patched Server.do_GET().
        
        Fallback order:
        1. Thread-local storage (set by patched server).
        2. App.path attribute (may not be set yet).
        3. kwargs['_router_path'] (if passed explicitly).
        4. Default path.
        
        Returns:
            str: The requested URL path.
        """
        # Check thread-local storage first (from patched server).
        if hasattr(_thread_local, 'current_path'):
            path = _thread_local.current_path
            log.debug(f'RouterApp: Got path from thread-local: {path}')
            return path
        
        # Check if path is already set as an attribute.
        if hasattr(self, 'path') and self.path:
            log.debug(f'RouterApp: Got path from self.path: {self.path}')
            return self.path
        
        # Check kwargs (if passed explicitly).
        if '_router_path' in self._kwargs:
            path = self._kwargs['_router_path']
            log.debug(f'RouterApp: Got path from kwargs: {path}')
            return path
        
        # Fallback to default.
        log.warning('RouterApp: Could not determine path, using default')
        return self._default_path
    
    def main(self, *userdata):
        """Main entry point called by REMI.
        
        REMI calls this after __init__() to get the root widget.
        We delegate to the target App's main() method.
        
        Args:
            *userdata: User data tuple from start() function.
        
        Returns:
            Widget: The root widget for this App.
        """
        log.debug(f'RouterApp.main() called for path {self._requested_path}')
        
        # Delegate to target App's main().
        root_widget = self._target_app.main(*userdata)
        
        # Store the root widget.
        self._root_widget = root_widget
        
        return root_widget
    
    def idle(self):
        """Idle callback called periodically by REMI.
        
        We delegate to the target App's idle() method.
        """
        if hasattr(self._target_app, 'idle'):
            return self._target_app.idle()
    
    def __getattribute__(self, name):
        """Intercept ALL attribute access to proxy to target App.
        
        This makes RouterApp completely transparent. Any attribute access
        (including identifier, path, etc.) is forwarded to the target App.
        
        Args:
            name (str): Attribute name.
        
        Returns:
            Any: The attribute value, either from RouterApp or target App.
        """
        # RouterApp's own private attributes - access directly.
        # These are needed for the proxying mechanism itself.
        router_private_attrs = {
            '_userdata', '_kwargs', '_requested_path', '_target_app',
            '_target_class', '_is_initialized', '__class__', '__dict__'
        }
        
        if name in router_private_attrs:
            return object.__getattribute__(self, name)
        
        # Check if RouterApp is fully initialized.
        try:
            target = object.__getattribute__(self, '_target_app')
        except AttributeError:
            # Not yet initialized, return from self.
            return object.__getattribute__(self, name)
        
        # Delegate to target App.
        return getattr(target, name)
    
    def __setattr__(self, name, value):
        """Intercept attribute setting to proxy to target App.
        
        Args:
            name (str): Attribute name.
            value: Attribute value.
        """
        # RouterApp's own private attributes - set directly on self.
        router_private_attrs = {
            '_userdata', '_kwargs', '_requested_path', '_target_app',
            '_target_class', '_is_initialized'
        }
        
        if name in router_private_attrs:
            object.__setattr__(self, name, value)
            return
        
        # Check if RouterApp is fully initialized.
        try:
            target = object.__getattribute__(self, '_target_app')
            # Delegate to target App.
            setattr(target, name, value)
        except AttributeError:
            # Not yet initialized, set on self.
            object.__setattr__(self, name, value)


# Thread-local storage for passing request context from server to App.__init__().
_thread_local = threading.local()


# Store original Server.do_GET for restoration if needed.
_original_server_do_GET = None


def start(app_class_or_routes, *args, **kwargs):
    """
    Enhanced start() function that supports routing.
    
    This function wraps REMI's start() to provide multi-path routing.
    It patches REMI's Server class to intercept requests and store paths.
    
    Usage:
        # Option 1: Pass routes dict directly.
        routes = {'/': MainGui, '/say': SayGui}
        start(routes, userdata=(...), address='0.0.0.0', port=8081, ...)
        
        # Option 2: Pass single App class (backward compatible).
        start(WebGui, userdata=(...), address='0.0.0.0', port=8081, ...)
    
    Args:
        app_class_or_routes: Either a dict of routes {path: AppClass} or a single App class.
        *args: Positional arguments for REMI's start().
        **kwargs: Keyword arguments for REMI's start().
            Special kwargs for routing:
                - default_path (str): Default path (default: '/').
    
    Returns:
        The return value from REMI's start() function.
    """
    # Check if we have routes dict or single App class.
    if isinstance(app_class_or_routes, dict):
        # Routes dict provided.
        routes = app_class_or_routes
        default_path = kwargs.pop('default_path', '/')
        
        # Register routes with RouterApp.
        RouterApp.register_routes(routes, default_path)
        
        # Use RouterApp as the App class for REMI.
        app_class = RouterApp
    else:
        # Single App class provided (backward compatible mode).
        # Create a simple route mapping.
        app_class = app_class_or_routes
        routes = {'/': app_class}
        default_path = '/'
        
        # Register routes.
        RouterApp.register_routes(routes, default_path)
        
        # Use RouterApp.
        app_class = RouterApp
    
    log.info(f'Starting REMI server with routing: {list(routes.keys())}')
    
    # Patch REMI Server to intercept paths.
    _patch_remi_server()
    
    # Call REMI's original start() with RouterApp.
    try:
        return remi_start(app_class, *args, **kwargs)
    finally:
        # Cleanup: unpatch server.
        # Note: This won't be reached if start() blocks forever.
        # In practice, start() runs the server loop, so this is for cleanup on exception.
        log.debug('REMI start() returned, cleaning up patches')
        _unpatch_remi_server()

