"""
REMI Multi-Path Router Extension

This module extends REMI framework to support multiple URL paths with different App instances.

REMI Architecture Analysis:
============================
1. ThreadedHTTPServer receives HTTP requests.
2. For WebSocket connections, REMI creates ONE App instance per client.
3. App.__init__(*userdata) is called, then App.main(*userdata) is called.
4. App.path attribute is set by REMI BEFORE main() is called.
5. The returned widget from main() becomes the root widget for that client.

Key Insight:
- App.path IS available in main() method.
- We can check path in main() and delegate to appropriate UI builder.
- No server patching needed!

Solution Strategy:
==================
Simplified approach without server patching:

1. **RouterApp**: Single App class that REMI instantiates normally.
2. **Path Detection in main()**: Check self.path in main() method.
3. **Dynamic Delegation**: Call appropriate target App's main() based on path.
4. **Transparent Proxying**: Proxy all attributes to active target App.

This approach:
- NO server patching required.
- Works entirely within REMI's App lifecycle.
- Path is available in main() method.
- Clean and simple implementation.
"""

import logging
import remi.gui as gui
from remi import App, start as remi_start
from remi.server import runtimeInstances
import threading


log = logging.getLogger('remi.router')


class RouterApp(App):
    """
    Router App that delegates to different target Apps based on URL path.
    
    This is the ONLY App class registered with REMI server.
    It checks self.path in main() method and creates the appropriate
    target App instance dynamically.
    
    Key Insight:
    - REMI sets self.path BEFORE calling main().
    - We can check path in main() and create target App there.
    - Target App's main() returns the widget tree.
    - We store target App reference for attribute delegation.
    
    Architecture:
    - REMI creates ONE RouterApp instance per WebSocket client.
    - RouterApp.main() checks self.path.
    - RouterApp creates appropriate target App (MainGui, SayGui, etc.).
    - RouterApp calls target.main(*userdata) and returns the widget.
    - All subsequent attribute access is delegated to target App.
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
        We just store userdata and call parent __init__.
        The actual routing happens in main() where self.path is available.
        
        Args:
            *userdata: User data tuple from start() function.
            **kwargs: Additional keyword arguments (from REMI internals).
        """
        # Store userdata for later use in main().
        self._userdata = userdata
        self._kwargs = kwargs
        
        # Target App will be created in main().
        self._target_app = None
        self._target_class = None
        
        # Call parent __init__ to set up REMI internals.
        super().__init__(*userdata, **kwargs)
        
        log.debug(f'RouterApp.__init__ called, identifier={self.identifier}')
    
    def main(self, *userdata):
        """Main entry point called by REMI.
        
        REMI calls this after __init__() to get the root widget.
        At this point, self.path is set by REMI.
        
        We check self.path, create the appropriate target App, and
        delegate to its main() method.
        
        Args:
            *userdata: User data tuple from start() function.
        
        Returns:
            Widget: The root widget for this App.
        """
        # Get the requested path from self.path (set by REMI).
        requested_path = getattr(self, 'path', '/')
        
        # Clean up path (remove query string).
        if '?' in requested_path:
            requested_path = requested_path.split('?')[0]
        
        log.info(f'RouterApp.main() called for path: {requested_path}')
        
        # Select target App class based on path.
        with self._routes_lock:
            target_class = self._routes.get(requested_path)
            
            # Try prefix matching if exact match fails.
            if target_class is None and requested_path != '/':
                for route_path in sorted(self._routes.keys(), key=len, reverse=True):
                    if route_path != '/' and requested_path.startswith(route_path):
                        target_class = self._routes[route_path]
                        log.debug(f'Prefix match: {requested_path} -> {route_path}')
                        break
            
            # Fallback to default path.
            if target_class is None:
                log.warning(f'No route found for {requested_path}, using default {self._default_path}')
                requested_path = self._default_path
                target_class = self._routes.get(self._default_path)
            
            if target_class is None:
                raise ValueError(f'No App class registered for path: {requested_path}')
        
        log.info(f'RouterApp routing {requested_path} -> {target_class.__name__}')
        
        # Create target App instance.
        # IMPORTANT: We create a NEW instance, passing the same userdata.
        # The target App's __init__ will call App.__init__ which sets up REMI internals.
        try:
            self._target_app = target_class(*userdata, **self._kwargs)
            self._target_class = target_class
        except Exception as e:
            log.exception(f'Failed to create target App {target_class.__name__}: {e}')
            raise
        
        # Call target App's main() method to get the root widget.
        try:
            root_widget = self._target_app.main(*userdata)
        except Exception as e:
            log.exception(f'Failed to call main() on {target_class.__name__}: {e}')
            raise
        
        log.debug(f'RouterApp.main() returning widget from {target_class.__name__}')
        
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


def start(app_class_or_routes, *args, **kwargs):
    """
    Enhanced start() function that supports routing.
    
    This function wraps REMI's start() to provide multi-path routing.
    
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
    
    # Call REMI's original start() with RouterApp.
    # No server patching needed - path is available in main().
    return remi_start(app_class, *args, **kwargs)

