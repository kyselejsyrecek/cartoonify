"""
DEPRECATED: Reverse Proxy Implementation

This reverse proxy approach has been DEPRECATED and should NOT be used.

REASON FOR DEPRECATION:
The REMI library has hardcoded assumptions that applications run at the server root path.
Both HTML and JavaScript code reference external files (CSS, JS, resources) using absolute
paths starting from the root (e.g., /res:style.css, /internal_js). This makes it impossible
for a reverse proxy to unambiguously route requests, as requests like /favicon.ico or
/res:style.css cannot be definitively mapped to a specific backend application when multiple
applications are mounted at different path prefixes (e.g., / and /say).

ALTERNATIVE APPROACH:
Instead of using a reverse proxy with path-based routing, applications should be served:
1. On separate ports (e.g., MainWebGui on :80, SayWebGui on :2001)
2. On subdomains (e.g., main.hostname.local on :80, say.hostname.local on :80)

This file is preserved for historical reference only.

================================================================================
ORIGINAL IMPLEMENTATION (DO NOT USE)
================================================================================

Example of how this reverse proxy was instantiated and used:

    from app.gui.webgui import WebGuiProxy
    from app.gui.app import MainWebGui, SayWebGui
    
    # Create proxy instance.
    proxy = WebGuiProxy(
        listen_host='0.0.0.0',      # Listen on all interfaces.
        listen_port=8081,            # External port for proxy.
        cert_file='/etc/ssl/certs/ssl-cert-snakeoil.pem',  # TLS certificate.
        key_file='/etc/ssl/private/ssl-cert-snakeoil.key'  # TLS private key.
    )
    
    # Register backend applications.
    # MainWebGui served at root path '/'.
    proxy.register_app(MainWebGui, host='127.0.0.1', port=2000)
    
    # SayWebGui served at '/say' path.
    proxy.register_app(SayWebGui, host='127.0.0.1', port=2001)
    
    # Start the proxy server.
    proxy.start()
    
    # When done, stop the proxy.
    # proxy.stop()

Routes were configured in routes.py:
    
    routes = {
        '/': {
            'gui_class': MainWebGui,
            'description': 'Main camera/capture interface'
        },
        '/say': {
            'gui_class': SayWebGui,
            'description': 'Text-to-speech interface'
        }
    }

The proxy would:
1. Accept external requests on 0.0.0.0:8081
2. Match request path to route (longest prefix match)
3. Forward to appropriate backend (127.0.0.1:2000 or 127.0.0.1:2001)
4. Strip path prefix before forwarding (e.g., /say/api -> /api)

This approach failed because REMI's internal resource paths (like /res:style.css)
were ambiguous - the proxy couldn't determine which backend should handle them.

================================================================================
"""

import asyncio
import logging
import threading

from app.debugging.logging import getLogger


# Route configuration (moved from routes.py).
routes = {
    '/': {
        'gui_class': 'MainWebGui',  # String reference to avoid import.
        'description': 'Main camera/capture interface'
    },
    '/say': {
        'gui_class': 'SayWebGui',  # String reference to avoid import.
        'description': 'Text-to-speech interface'
    }
}


class WebGuiProxy:
    """
    DEPRECATED: Reverse proxy using mitmproxy.
    
    DO NOT USE - See module docstring for deprecation reason.
    
    Original usage:
        proxy = WebGuiProxy(
            listen_host='0.0.0.0',
            listen_port=8081,
            cert_file='/path/to/cert.pem',
            key_file='/path/to/key.pem'
        )
        proxy.register_app(MainWebGui, '127.0.0.1', 2000)
        proxy.register_app(SayWebGui, '127.0.0.1', 2001)
        proxy.start()
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
        
        self._log.warning('WebGuiProxy is DEPRECATED and should not be used. See reverse_proxy.py for details.')
    
    def register_app(self, app_class, host, port):
        """Register an app and its routes for the proxy."""
        self._routes[f'/{app_class.__name__.lower()}'] = {'host': host, 'port': port}
        self._log.debug(f'Registered route: /{app_class.__name__.lower()} -> {host}:{port}')
    
    def start(self):
        """Start the proxy (DEPRECATED)."""
        self._log.error('Cannot start deprecated WebGuiProxy. Use direct application hosting instead.')
        raise NotImplementedError('WebGuiProxy is deprecated. Use subdomain or port-based hosting.')
    
    def stop(self):
        """Stop the proxy."""
        self._stop_event.set()
    
    def _run_proxy(self):
        """Run mitmproxy in dedicated asyncio event loop (DEPRECATED)."""
        raise NotImplementedError('WebGuiProxy is deprecated.')


class WebGuiProxyAddon:
    """DEPRECATED: mitmproxy addon for request routing."""
    
    def __init__(self, routes):
        self._routes = routes
        self._log = getLogger(self.__class__.__name__)
        self._log.warning('WebGuiProxyAddon is DEPRECATED.')
    
    def request(self, flow):
        """Handle incoming requests (DEPRECATED)."""
        raise NotImplementedError('WebGuiProxyAddon is deprecated.')
