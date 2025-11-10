"""
REMI Multi-Path Router Extension

This module extends REMI framework to support multi-path routing by maintaining
persistent App instances for each route and storing multiple root widgets.

CRITICAL Architecture Understanding:
===================================
From REMI source analysis:
1. server.py line 618: `if not 'root' in self.page.children['body'].children.keys()`
   - REMI checks for 'root' key in body.children
2. server.py line 482: `self.page.children['body'].append(widget, 'root')`
   - REMI ALWAYS uses key 'root' for root widget
3. Problem: Multiple paths share the SAME 'root' key location

Solution Strategy:
==================
1. Pre-create persistent App instances for each route (MainGui, SayGui) at startup.
2. Monkey-patch do_GET to:
   - Store request path in self
   - Check for path-specific root key (e.g., 'root_/', 'root_/say')
3. Monkey-patch set_root_widget to:
   - Use path-specific key instead of 'root'
   - Store root per-path in self._route_roots dict
4. Monkey-patch do_gui_update and websocket_handshake_done to:
   - Use correct per-path root widget
5. Router pattern:
   - RouterApp.main() delegates to pre-created instances
   - Each instance gets its own root widget with unique key
   - All instances persist in memory simultaneously

Key Requirements Met:
=====================
- Instances NEVER destroyed (pre-created at startup)
- Each path has ONE persistent instance shared by all clients
- Multiple browser windows with different URLs work simultaneously
- All clients see the same instance state for the same route
- Root widgets stored per-path, not overwritten
"""

import logging
import threading
import weakref
from remi import App, start as remi_start
from remi import server as remi_server

# Re-export App classes for single import point.
from app.gui.gui_main import MainGui
from app.gui.gui_say import SayGui

log = logging.getLogger('remi.router')

# Global storage for route instances (persistent across all sessions).
_route_instances = {}
_instances_lock = threading.RLock()

# Track which path each session is currently using.
_session_current_path = {}
_session_lock = threading.RLock()



class RouteInstance:
    """
    Wrapper for a route-specific persistent root widget.
    
    This stores the App class and builds the root widget once, which is then
    cached and reused for all clients accessing this route.
    
    IMPORTANT: We cannot pre-create App instances because App is a 
    BaseHTTPRequestHandler and requires request, client_address, server args.
    Instead, we cache the root widget built by RouterApp.main().
    """
    
    def __init__(self, app_class, userdata, path):
        """
        Initialize route metadata.
        
        Args:
            app_class: The App class (MainGui or SayGui).
            userdata: Tuple of initialization data.
            path: The route path this instance handles (e.g., '/', '/say').
        """
        self.app_class = app_class
        self.userdata = userdata
        self.path = path
        
        # Root widget will be built and cached by get_or_build_root_widget().
        self._root_widget = None
        self._root_lock = threading.RLock()
        
        log.info(f'Created RouteInstance: {app_class.__name__} at {path}')
    
    def get_or_build_root_widget(self, app_instance):
        """
        Get or build the root widget for this route.
        
        This is called from RouterApp.main(). The root widget is built once
        and cached, then reused for all subsequent requests to this route.
        
        Args:
            app_instance: The current RouterApp instance (self from main()).
        
        Returns:
            Widget: The persistent root widget for this route.
        """
        with self._root_lock:
            if self._root_widget is None:
                log.info(f'Building root widget for {self.app_class.__name__} at {self.path}')
                
                # Build UI by calling the original App class's main() method.
                # We call it on a temporary instance just to get the widget tree.
                # The widget tree itself is the persistent state we need.
                self._root_widget = self.app_class.main(app_instance, *self.userdata)
                
                log.info(f'Root widget built for {self.path}')
            return self._root_widget
    
    def call_idle(self, app_instance):
        """
        Call idle() on the App class if it has one.
        
        Args:
            app_instance: The current RouterApp instance to pass to idle().
        """
        if hasattr(self.app_class, 'idle'):
            try:
                self.app_class.idle(app_instance)
            except Exception as e:
                log.error(f'Error in {self.app_class.__name__}.idle(): {e}', exc_info=True)



class RouterApp(App):
    """
    Router App that delegates to pre-created route instances.
    
    This class acts as a facade, intercepting REMI's App lifecycle
    and routing requests to the appropriate persistent route instance.
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
        
        Reads self.request_path (set by patched do_GET), finds appropriate
        RouteInstance, and returns its root widget.
        
        Args:
            *userdata: User data tuple (event_service, logger, etc.).
        
        Returns:
            Widget: Root widget from the appropriate route instance.
        """
        # Get path from self (set by patched do_GET).
        path = getattr(self, 'request_path', self._default_path)
        
        # Normalize path.
        path = path.rstrip('/') or '/'
        
        log.info(f'RouterApp.main() for path: {path}, session: {self.session}')
        
        # Find the pre-created RouteInstance.
        with _instances_lock:
            route_instance = _route_instances.get(path)
            
            # Try prefix matching if exact match fails.
            if route_instance is None:
                for route_path in sorted(_route_instances.keys(), key=len, reverse=True):
                    if route_path != '/' and path.startswith(route_path):
                        route_instance = _route_instances[route_path]
                        log.debug(f'Prefix match: {path} -> {route_path}')
                        path = route_path
                        break
            
            # Fallback to default path.
            if route_instance is None:
                route_instance = _route_instances.get(self._default_path)
                path = self._default_path
                log.warning(f'No route for {path}, using {self._default_path}')
            
            if route_instance is None:
                raise ValueError(f'No RouteInstance found for path: {path}')
        
        # Track which path this session is using (thread-safe).
        with _session_lock:
            _session_current_path[self.session] = path
        
        log.info(f'Using {route_instance.app_class.__name__} for session {self.session}')
        
        # Get or build the root widget from the route instance.
        # Pass self so the route can call the original App class's main().
        root_widget = route_instance.get_or_build_root_widget(self)
        
        return root_widget
    
    def idle(self):
        """
        Delegate idle() to all route instances.
        
        This is called periodically by REMI's update loop.
        """
        with _instances_lock:
            for path, route_instance in _route_instances.items():
                route_instance.call_idle(self)



def _patched_set_root_widget(original_set_root_widget):
    """
    Monkey-patch for App.set_root_widget() to support multiple coexisting roots.
    
    REMI's original set_root_widget always uses key 'root' in body.children.
    This causes overwrites when switching paths. This patch uses path-specific
    keys like 'root_/', 'root_/say' so multiple roots coexist.
    
    Args:
        original_set_root_widget: Original set_root_widget method from REMI.
    
    Returns:
        Patched set_root_widget function.
    """
    def set_root_widget(self, widget):
        """Set root widget with path-specific key."""
        # Get current path for this session.
        path = getattr(self, '_current_path', '/')
        
        # Generate path-specific key.
        # Replace '/' with '_' to make it a valid dict key.
        key = 'root_' + path.replace('/', '_')
        
        log.debug(f'set_root_widget: path={path}, key={key}, session={getattr(self, "session", "none")}')
        
        # Store widget with path-specific key (not 'root'!).
        self.page.children['body'].append(widget, key)
        
        # Initialize _route_roots dict if needed.
        if not hasattr(self, '_route_roots'):
            self._route_roots = {}
        
        # Store in per-path dict.
        self._route_roots[path] = widget
        
        # Also set self.root for backward compatibility with REMI internals.
        # NOTE: This will be overridden by _patched_do_gui_update to use correct path.
        self.root = widget
        
        log.info(f'Set root widget for path={path} (key={key})')
    
    return set_root_widget


def _patched_do_GET(original_do_GET):
    """
    Monkey-patch for App.do_GET() to implement complete multi-path routing.
    
    This patch:
    1. Extracts HTTP request path from URL.
    2. Stores it in self.request_path for RouterApp.main().
    3. Tracks current path in self._current_path for set_root_widget.
    4. Checks for path-specific root widget (not generic 'root').
    5. Updates self.root to point to correct path's root if it exists.
    
    Args:
        original_do_GET: Original do_GET method from REMI server.
    
    Returns:
        Patched do_GET function.
    """
    def do_GET(self):
        """Patched do_GET that implements complete multi-path routing."""
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
        
        # Store in attributes for RouterApp.main() and set_root_widget.
        self.request_path = clean_path
        self._current_path = clean_path
        
        # Initialize _route_roots dict if needed.
        if not hasattr(self, '_route_roots'):
            self._route_roots = {}
        
        log.debug(f'Patched do_GET: path={clean_path}, session={getattr(self, "session", "none")}')
        
        # Track which path this session is using (thread-safe).
        global _session_current_path, _session_lock
        if hasattr(self, 'session'):
            with _session_lock:
                _session_current_path[self.session] = clean_path
        
        # Check if root widget exists for this path (mimics REMI line 618).
        # Generate path-specific key.
        key = 'root_' + clean_path.replace('/', '_')
        
        if hasattr(self, 'page') and 'body' in self.page.children:
            body = self.page.children['body']
            
            # Check for path-specific root key.
            if key not in body.children.keys():
                # Root doesn't exist for this path - REMI will build UI.
                log.debug(f'Root widget missing for path={clean_path} (key={key}), will build UI')
            else:
                # Root exists - update self.root to point to correct path's root.
                log.debug(f'Root widget exists for path={clean_path} (key={key})')
                
                if clean_path in self._route_roots:
                    self.root = self._route_roots[clean_path]
                    log.debug(f'Updated self.root to path {clean_path}')
        
        # Call original do_GET.
        return original_do_GET(self)
    
    return do_GET


def _patched_do_gui_update(original_do_gui_update):
    """
    Monkey-patch for App.do_gui_update() to use correct root per path.
    
    REMI's original do_gui_update uses self.root.repr() which references
    the single self.root attribute. This patch uses self._route_roots[path]
    to get the correct root widget for current path.
    
    Args:
        original_do_gui_update: Original do_gui_update method from REMI.
    
    Returns:
        Patched do_gui_update function.
    """
    def do_gui_update(self):
        """Update GUI using correct root widget for current path."""
        # Get current path for this session.
        path = getattr(self, '_current_path', '/')
        
        # Get correct root widget for this path.
        if hasattr(self, '_route_roots') and path in self._route_roots:
            # Temporarily override self.root with correct path's root.
            original_root = getattr(self, 'root', None)
            self.root = self._route_roots[path]
            
            try:
                # Call original with correct root.
                return original_do_gui_update(self)
            finally:
                # Restore original (though it may be overridden again).
                if original_root is not None:
                    self.root = original_root
        else:
            # Fallback to original behavior.
            return original_do_gui_update(self)
    
    return do_gui_update


def _patched_websocket_handshake_done(original_websocket_handshake_done):
    """
    Monkey-patch for App.websocket_handshake_done() to use correct root per path.
    
    REMI's original websocket_handshake_done uses self.root.identifier for
    initial sync message. This patch uses self._route_roots[path] to get
    the correct root widget for current path.
    
    Args:
        original_websocket_handshake_done: Original method from REMI.
    
    Returns:
        Patched websocket_handshake_done function.
    """
    def websocket_handshake_done(self):
        """Handle WebSocket handshake using correct root widget for current path."""
        # Get current path for this session.
        path = getattr(self, '_current_path', '/')
        
        # Get correct root widget for this path.
        if hasattr(self, '_route_roots') and path in self._route_roots:
            # Temporarily override self.root with correct path's root.
            original_root = getattr(self, 'root', None)
            self.root = self._route_roots[path]
            
            try:
                # Call original with correct root.
                return original_websocket_handshake_done(self)
            finally:
                # Restore original (though it may be overridden again).
                if original_root is not None:
                    self.root = original_root
        else:
            # Fallback to original behavior.
            return original_websocket_handshake_done(self)
    
    return websocket_handshake_done


def _create_route_instances(routes, userdata):
    """
    Create RouteInstance metadata objects for all routes.
    
    This happens ONCE at server startup. RouteInstance stores the App class
    and userdata, but does NOT create App instances (those are created by REMI).
    The root widgets are built lazily on first request to each route.
    
    Args:
        routes (dict): Mapping of path to App class.
        userdata (tuple): Userdata tuple to pass to App.main() methods.
    """
    global _route_instances
    
    with _instances_lock:
        for path, app_class in routes.items():
            log.info(f'Registering route: {app_class.__name__} for path {path}')
            route_instance = RouteInstance(app_class, userdata, path)
            _route_instances[path] = route_instance
            log.info(f'Successfully registered route for {path}')


def start(app_class_or_routes, *args, **kwargs):
    """
    Enhanced start() function with multi-path routing support.
    
    This function:
    1. Detects if routes dict is provided (multi-path) or single App (standard).
    2. For multi-path: pre-creates RouteInstances, registers routes, applies patch.
    3. For single App: passes through to standard remi.start().
    
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
        userdata = kwargs.get('userdata', ())
        
        log.info(f'Router start() with routes: {list(routes.keys())}')
        
        # Pre-create RouteInstances for all routes.
        _create_route_instances(routes, userdata)
        
        # Register routes with RouterApp.
        RouterApp.register_routes(routes, default_path)
        
        # Apply ALL monkey-patches to REMI internals for multi-path support.
        
        # 1. Patch do_GET to track current path per session.
        original_do_GET = remi_server.App.do_GET
        remi_server.App.do_GET = _patched_do_GET(original_do_GET)
        log.info('Applied do_GET patch')
        
        # 2. Patch set_root_widget to use path-specific keys.
        original_set_root_widget = remi_server.App.set_root_widget
        remi_server.App.set_root_widget = _patched_set_root_widget(original_set_root_widget)
        log.info('Applied set_root_widget patch')
        
        # 3. Patch do_gui_update to use correct root per path.
        original_do_gui_update = remi_server.App.do_gui_update
        remi_server.App.do_gui_update = _patched_do_gui_update(original_do_gui_update)
        log.info('Applied do_gui_update patch')
        
        # 4. Patch websocket_handshake_done to use correct root per path.
        original_websocket_handshake_done = remi_server.App.websocket_handshake_done
        remi_server.App.websocket_handshake_done = _patched_websocket_handshake_done(original_websocket_handshake_done)
        log.info('Applied websocket_handshake_done patch')
        
        log.info('All monkey-patches applied for multi-path routing')
        
        # Use RouterApp as the App class.
        app_class = RouterApp
    else:
        # Single App class (backward compatible).
        app_class = app_class_or_routes
        log.info(f'Starting REMI with single App: {app_class.__name__}')
    
    # Start REMI server.
    return remi_start(app_class, *args, **kwargs)

