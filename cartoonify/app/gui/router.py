"""
REMI Multi-Path Router Extension

This module extends REMI framework to support multi-path routing by monkey-patching
the server's do_GET method to set path attribute before main() is called.

Architecture:
1. RouterApp stores route mappings in class variable.
2. Monkey-patch applied to server handler before starting REMI.
3. do_GET sets self.path based on HTTP request path.
4. RouterApp.main() reads self.path and delegates to appropriate App class.
5. Each route gets its own root widget, avoiding cross-contamination.

This approach preserves REMI's session management while adding path-based routing.
"""

import logging
from remi import App, start as remi_start
from remi import server as remi_server

# Re-export App classes for single import point.
from app.gui.gui_main import MainGui
from app.gui.gui_say import SayGui

log = logging.getLogger('remi.router')


class RouterApp(App):
    """
    Router App that delegates to appropriate App class based on request path.
    
    This class stores route mappings and implements main() to instantiate
    and return the correct App's root widget based on self.path.
    """
    
    # Class variable to store route mappings.
    _routes = {}
    _default_path = '/'
    
    @classmethod
    def register_routes(cls, routes, default_path='/'):
        """
        Register route mappings.
        
        Args:
            routes (dict): Mapping of path to App class {'/': MainGui, '/say': SayGui}.
            default_path (str): Default path to use if none matches.
        """
        cls._routes = routes
        cls._default_path = default_path
        log.info(f'Registered routes: {list(routes.keys())}, default={default_path}')
    
    def main(self, *userdata):
        """
        Main entry point called by REMI when building UI.
        
        Reads self.request_path (set by patched do_GET), finds appropriate App class,
        instantiates it with userdata, and returns its root widget.
        
        Returns:
            Widget: Root widget from the appropriate App instance.
        """
        # Get path from self (set by patched do_GET).
        path = getattr(self, 'request_path', self._default_path)
        
        # Normalize path.
        path = path.rstrip('/') or '/'
        
        log.info(f'RouterApp.main() for path: {path}')
        
        # Find matching App class.
        app_class = self._routes.get(path)
        
        # Try prefix matching if exact match fails.
        if app_class is None:
            for route_path in sorted(self._routes.keys(), key=len, reverse=True):
                if route_path != '/' and path.startswith(route_path):
                    app_class = self._routes[route_path]
                    log.debug(f'Prefix match: {path} -> {route_path}')
                    break
        
        # Fallback to default path.
        if app_class is None:
            app_class = self._routes.get(self._default_path)
            log.warning(f'No route for {path}, using {self._default_path}')
        
        if app_class is None:
            raise ValueError(f'No App class found for path: {path}')
        
        log.info(f'Instantiating {app_class.__name__} for path: {path}')
        
        # Instantiate App and return its root widget.
        app_instance = app_class(*userdata)
        root_widget = app_instance.main(*userdata)
        
        return root_widget


def _patched_do_GET(original_do_GET):
    """
    Creates a patched do_GET that manages path-based routing.
    
    This patch:
    1. Extracts HTTP request path.
    2. Stores it in self.request_path for RouterApp.main().
    3. Removes cached 'root' widget if path changed, forcing REMI to call main() again.
    
    Args:
        original_do_GET: Original do_GET method from REMI server.
    
    Returns:
        Patched do_GET function.
    """
    def do_GET(self):
        """Patched do_GET that implements path-based routing."""
        # Extract path from HTTP request.
        try:
            from urllib.parse import unquote, urlparse
        except ImportError:
            from urlparse import unquote, urlparse
        
        # self.path is the HTTP request path (builtin attribute).
        http_path = str(unquote(self.path))
        
        # Parse path (remove query string).
        parsed = urlparse(http_path)
        clean_path = parsed.path
        
        # Normalize path.
        clean_path = clean_path.rstrip('/') or '/'
        
        # Store in SEPARATE attribute for RouterApp.main().
        self.request_path = clean_path
        
        log.debug(f'Patched do_GET: request_path={clean_path}')
        
        # Check if path changed from previous request.
        # If yes, remove cached root to force REMI to call main() again.
        previous_path = getattr(self, '_previous_request_path', None)
        if previous_path is not None and previous_path != clean_path:
            # Path changed - remove cached root widget.
            if hasattr(self, 'page') and 'body' in self.page.children:
                body = self.page.children['body']
                if 'root' in body.children:
                    log.info(f'Path changed {previous_path} -> {clean_path}, removing cached root')
                    body.children.pop('root', None)
                    if 'root' in body._render_children_list:
                        body._render_children_list.remove('root')
        
        # Remember current path for next request.
        self._previous_request_path = clean_path
        
        # Call original do_GET.
        return original_do_GET(self)
    
    return do_GET


def start(app_class_or_routes, *args, **kwargs):
    """
    Enhanced start() function with multi-path routing support.
    
    Usage:
        # Multi-path routing.
        routes = {'/': MainGui, '/say': SayGui}
        start(routes, userdata=(...), address='0.0.0.0', port=8081, ...)
        
        # Single App (backward compatible).
        start(MainGui, userdata=(...), address='0.0.0.0', port=8081, ...)
    
    Args:
        app_class_or_routes: Either dict {path: AppClass} or single App class.
        *args: Positional arguments for remi.start().
        **kwargs: Keyword arguments for remi.start().
            Special kwarg: default_path (str) - default route (default '/').
    
    Returns:
        Result from remi.start().
    """
    # Check if routing is requested.
    if isinstance(app_class_or_routes, dict):
        routes = app_class_or_routes
        default_path = kwargs.pop('default_path', '/')
        
        # Register routes with RouterApp.
        RouterApp.register_routes(routes, default_path)
        
        # Monkey-patch do_GET to set path attribute.
        original_do_GET = remi_server.App.do_GET
        remi_server.App.do_GET = _patched_do_GET(original_do_GET)
        
        log.info('Applied do_GET patch for multi-path routing')
        
        # Use RouterApp as the App class.
        app_class = RouterApp
    else:
        # Single App class (backward compatible).
        app_class = app_class_or_routes
        log.info(f'Starting REMI with single App: {app_class.__name__}')
    
    # Start REMI server.
    return remi_start(app_class, *args, **kwargs)
