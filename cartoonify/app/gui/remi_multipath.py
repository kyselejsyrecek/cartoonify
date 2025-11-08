"""
Multi-path routing support for REMI framework.

This module extends REMI's App class to support multiple concurrent sessions
with different URL paths, allowing multiple browser tabs to access different
pages simultaneously without widget ID conflicts.
"""

import weakref
import logging
from remi import App as RemiApp
from remi import start as remi_start
from remi import server

log = logging.getLogger(__name__)


# Per-session storage for widget instances
# Key: session_id, Value: WeakValueDictionary of widget instances
_session_instances = {}
_original_runtimeInstances = server.runtimeInstances


class SessionAwareRuntimeInstances:
    """
    Proxy for runtimeInstances that maintains separate widget dictionaries per session.
    """
    
    def __init__(self):
        self._current_session_id = None
        self._default_instances = weakref.WeakValueDictionary()
        
    def set_current_session(self, session_id):
        """Set the current session ID for subsequent operations."""
        self._current_session_id = session_id
        if session_id not in _session_instances:
            _session_instances[session_id] = weakref.WeakValueDictionary()
    
    def _get_current_dict(self):
        """Get the runtime instances dict for the current session."""
        if self._current_session_id and self._current_session_id in _session_instances:
            return _session_instances[self._current_session_id]
        return self._default_instances
    
    def __getitem__(self, key):
        return self._get_current_dict()[key]
    
    def __setitem__(self, key, value):
        self._get_current_dict()[key] = value
    
    def __delitem__(self, key):
        del self._get_current_dict()[key]
    
    def __contains__(self, key):
        return key in self._get_current_dict()
    
    def get(self, key, default=None):
        return self._get_current_dict().get(key, default)
    
    def keys(self):
        return self._get_current_dict().keys()
    
    def values(self):
        return self._get_current_dict().values()
    
    def items(self):
        return self._get_current_dict().items()


# Replace global runtimeInstances with session-aware version
_session_aware_instances = SessionAwareRuntimeInstances()
server.runtimeInstances = _session_aware_instances


class App(RemiApp):
    """
    Extended REMI App that supports multiple URL paths with separate sessions.
    
    Use this class instead of remi.App to get multi-path support.
    Each browser tab/window gets its own session with separate widget instances.
    """
    
    def __init__(self, *args, **kwargs):
        # Set session before calling parent __init__
        self._set_session_from_client()
        super(App, self).__init__(*args, **kwargs)
    
    def _set_session_from_client(self):
        """Extract session ID and set it in the session-aware runtimeInstances."""
        try:
            if hasattr(self, 'client_address'):
                session_id = f"{self.client_address[0]}:{self.client_address[1]}"
                _session_aware_instances.set_current_session(session_id)
        except:
            pass


def start(app_class, **kwargs):
    """
    Start the REMI server with multi-path support.
    
    Use this instead of remi.start() to get multi-path functionality.
    
    Args:
        app_class: Your App class (should inherit from remi_multipath.App)
        **kwargs: All arguments that remi.start() accepts
    """
    return remi_start(app_class, **kwargs)
