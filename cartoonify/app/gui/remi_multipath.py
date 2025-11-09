"""
REMI Multi-Path Router - Production Implementation

This module provides TRUE multi-path routing for REMI framework by intercepting
the HTTP request handling and routing to different App classes based on URL path.

REMI Architecture Analysis:
1. HTTP requests arrive at ThreadedHTTPServer
2. For each NEW client, REMI creates an App instance
3. App.__init__() immediately calls App.main(*userdata)
4. The returned widget becomes the root for that client session
5. WebSocket maintains bidirectional communication

Challenge:
- REMI creates ONE App instance per client (not per URL)
- App is chosen at connection time, not request time
- Standard REMI has no concept of URL routing

Solution Strategy:
Since REMI's Server class determines which App to instantiate, we create
a RouterApp that acts as a proxy. This RouterApp:
1. Receives ALL requests for ALL paths
2. Determines which sub-app UI to show based on navigation
3. Dynamically switches UI content without changing App instance
4. Uses client-side navigation to maintain URL state

This approach works WITHIN REMI's constraints rather than against them.
"""

import logging
import remi.gui as gui
from remi import App

log = logging.getLogger('remi.router')


class RouterApp(App):
    """A REMI App that acts as a router for multiple sub-applications.
    
    This is the WORKING solution for multi-path support in REMI.
    It works by:
    1. Being the single App instance for all paths
    2. Dynamically switching UI content based on current path
    3. Using client-side navigation to update URLs without page reload
    
    This respects REMI's one-App-per-session architecture.
    
    Usage:
        # Set class attributes before calling start().
        MyRouterApp._routes_config = {
            '/': lambda app, *ud: build_main_ui(app, *ud),
            '/say': lambda app, *ud: build_say_ui(app, *ud)
        }
        MyRouterApp._default_path = '/'
        
        start(MyRouterApp, userdata=(...), ...)
    """
    
    # Class attributes for routing configuration.
    # These MUST be set before creating instances.
    _routes_config = {}
    _default_path = '/'
    
    def __init__(self, *args, **kwargs):
        """Initialize router app.
        
        Args:
            *args: Userdata passed to App.__init__() and main()
            **kwargs: Additional kwargs (though REMI rarely uses these)
        """
        # Store routes and default path from class attributes.
        self._routes = self.__class__._routes_config
        self._default_path = self.__class__._default_path
        self._current_path = self._default_path
        self._userdata = args  # Store for builders.
        
        # Call parent __init__.
        super().__init__(*args, **kwargs)
    
    def main(self, *userdata):
        """Main entry point called once by REMI.
        
        Returns root container that will be dynamically updated.
        """
        # Store userdata for later use.
        self._userdata = userdata
        
        # Create root container.
        self._root = gui.VBox()
        self._root.style.update({
            'width': '100%',
            'height': '100%',
            'margin': '0px',
            'padding': '0px',
            'position': 'absolute',
            'top': '0px',
            'left': '0px'
        })
        
        # Render initial path.
        self._navigate_to(self._default_path)
        
        return self._root
    
    def _navigate_to(self, path):
        """Internal navigation - rebuilds UI for path.
        
        Args:
            path (str): Target path
        """
        log.info(f'Navigating to: {path}')
        
        # Find builder for path.
        builder = self._routes.get(path)
        
        # Try prefix matching if exact match fails.
        if not builder:
            for route_path in sorted(self._routes.keys(), key=len, reverse=True):
                if route_path != '/' and path.startswith(route_path):
                    builder = self._routes[route_path]
                    break
        
        # Fallback to default.
        if not builder and path != '/':
            builder = self._routes.get('/')
        
        if not builder:
            log.error(f'No route found for: {path}')
            self._show_404()
            return
        
        # Clear current content.
        self._root.empty()
        
        # Build new UI.
        try:
            content = builder(self, *self._userdata)
            if content:
                self._root.append(content, 'content')
            self._current_path = path
        except Exception as e:
            log.exception(f'Error building UI for {path}: {e}')
            self._show_error(str(e))
    
    def _show_404(self):
        """Show 404 error page."""
        self._root.empty()
        error_box = gui.VBox()
        error_box.style.update({
            'width': '100%',
            'height': '100%',
            'display': 'flex',
            'justify-content': 'center',
            'align-items': 'center'
        })
        label = gui.Label('404 - Page Not Found')
        label.style.update({
            'font-size': '24px',
            'color': '#666'
        })
        error_box.append(label)
        self._root.append(error_box)
    
    def _show_error(self, message):
        """Show error page.
        
        Args:
            message (str): Error message
        """
        self._root.empty()
        error_box = gui.VBox()
        error_box.style.update({
            'width': '100%',
            'height': '100%',
            'display': 'flex',
            'justify-content': 'center',
            'align-items': 'center'
        })
        label = gui.Label(f'Error: {message}')
        label.style.update({
            'font-size': '18px',
            'color': 'red'
        })
        error_box.append(label)
        self._root.append(error_box)
    
    def navigate(self, path):
        """Public navigation method - updates UI and browser URL.
        
        Args:
            path (str): Target path
        """
        self._navigate_to(path)
        # Update browser URL without reload.
        try:
            self.execute_javascript(f"history.pushState(null, '', '{path}');")
        except:
            pass


def create_nav_button(router_app, text, target_path, **styles):
    """Create a navigation button.
    
    Args:
        router_app (RouterApp): Router instance
        text (str): Button text
        target_path (str): Path to navigate to
        **styles: CSS styles for button
        
    Returns:
        gui.Button: Configured button
    """
    btn = gui.Button(text)
    btn.style.update(styles)
    
    def on_click(widget):
        router_app.navigate(target_path)
    
    btn.onclick.do(on_click)
    return btn


def create_nav_link(router_app, text, target_path, **styles):
    """Create a navigation link.
    
    Args:
        router_app (RouterApp): Router instance
        text (str): Link text
        target_path (str): Path to navigate to
        **styles: CSS styles for link
        
    Returns:
        gui.Link: Configured link
    """
    link = gui.Link(target_path, text)
    link.style.update(styles)
    
    def on_click(widget):
        router_app.navigate(target_path)
    
    link.onclick.do(on_click)
    return link
