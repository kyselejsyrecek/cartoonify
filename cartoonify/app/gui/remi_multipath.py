"""
Multi-application routing extension for REMI framework.

This module allows a single REMI server to serve different App classes
on different URL paths. Each path gets its own App instance with isolated
widget trees and event handling.

Usage:
    from app.gui.remi_multipath import MultiPathServer
    
    server = MultiPathServer()
    server.register_app('/', MainApp)
    server.register_app('/say', SayApp)
    server.start(address='0.0.0.0', port=80)
"""

import logging
import weakref
from remi import server as remi_server
from app.debugging.tracing import trace

log = logging.getLogger(__name__)


class MultiPathServer:
    """
    A REMI server wrapper that routes different URL paths to different App classes.
    
    This works by monkey-patching the REMI RequestHandler to check the path
    and instantiate the appropriate App class.
    """
    
    def __init__(self):
        self._routes = {}  # path -> app_class mapping
        self._app_instances = weakref.WeakValueDictionary()  # Track app instances per connection
        
    def register_app(self, path, app_class):
        """
        Register an App class to handle a specific URL path.
        
        Args:
            path (str): URL path (e.g., '/', '/say')
            app_class: REMI App class (not instance) to handle this path
        """
        # Normalize path
        if not path.startswith('/'):
            path = '/' + path
        
        self._routes[path] = app_class
        log.info(f"Registered {app_class.__name__} for path {path}")
    
    def start(self, **kwargs):
        """
        Start the multi-path REMI server.
        
        Args:
            **kwargs: All arguments accepted by remi.start() (address, port, etc.)
        """
        if not self._routes:
            raise ValueError("No apps registered. Use register_app() before start().")
        
        # Create a wrapper App class that routes based on path
        routes = self._routes
        app_instances = self._app_instances
        
        class MultiPathApp(remi_server.App):
            """
            Router App that delegates to the appropriate registered App based on URL path.
            """
            
            def __init__(self, *args, **kwargs):
                with trace():
                    # Determine which app to instantiate based on path.
                    self._target_app = None
                    self._target_app_class = None
                    
                    request_path = '/'
                    # Try to extract path from args (request handler is first arg).
                    if len(args) > 0 and hasattr(args[0], 'path'):
                        request_path = args[0].path
                    
                    log.debug(f"MultiPathApp.__init__: request_path = {request_path}")
                    
                    # Find matching route (exact match first, then prefix match).
                    matched_app_class = None
                    if request_path in routes:
                        matched_app_class = routes[request_path]
                    else:
                        # Try prefix matching for sub-paths.
                        for route_path, app_class in routes.items():
                            if request_path.startswith(route_path):
                                matched_app_class = app_class
                                break
                    
                    # Fallback to root if no match.
                    if matched_app_class is None:
                        matched_app_class = routes.get('/')
                    
                    if matched_app_class is None:
                        raise ValueError(f"No app registered for path {request_path} and no root (/) handler")
                    
                    self._target_app_class = matched_app_class
                    log.debug(f"MultiPathApp.__init__: Routing {request_path} to {matched_app_class.__name__}")
                    
                    # CRITICAL: We must call super().__init__() to properly initialize REMI App.
                    # This sets up all the internal REMI machinery (websockets, etc.).
                    super(MultiPathApp, self).__init__(*args, **kwargs)
                    
                    # Now instantiate the target app and copy its main() return value.
                    # We don't replace self with target - we just delegate main() calls.
                    self._target_app = matched_app_class(*args, **kwargs)
                    
                    # Store instance for tracking.
                    app_instances[id(self._target_app)] = self._target_app
                    
                    log.debug(f"MultiPathApp.__init__: Target app {matched_app_class.__name__} instantiated")
            
            def main(self, *args, **kwargs):
                """Route main() to the target app."""
                with trace():
                    log.debug(f"MultiPathApp.main: Calling target app main()")
                    if self._target_app and hasattr(self._target_app, 'main'):
                        result = self._target_app.main(*args, **kwargs)
                        log.debug(f"MultiPathApp.main: Target app main() returned")
                        return result
                    log.warning(f"MultiPathApp.main: No target app or no main() method")
                    return None
            
            def idle(self):
                """Route idle() to the target app."""
                with trace():
                    if self._target_app and hasattr(self._target_app, 'idle'):
                        return self._target_app.idle()
            
            def __getattr__(self, name):
                """Route any other method/attribute access to the target app."""
                if name.startswith('_'):
                    raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
                
                if self._target_app:
                    return getattr(self._target_app, name)
                
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        # Start REMI server with our router app
        return remi_server.start(MultiPathApp, **kwargs)


def start_multipath_server(apps_dict, **kwargs):
    """
    Convenient function to start a multi-path REMI server.
    
    Args:
        apps_dict (dict): Dictionary mapping paths to App classes
            Example: {'/' : MainApp, '/say': SayApp}
        **kwargs: Arguments for remi.start() (address, port, etc.)
    
    Returns:
        Server instance
    """
    server = MultiPathServer()
    for path, app_class in apps_dict.items():
        server.register_app(path, app_class)
    return server.start(**kwargs)
