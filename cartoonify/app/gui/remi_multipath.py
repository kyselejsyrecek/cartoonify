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


class SessionAwareRuntimeInstances:
    """
    Proxy for runtimeInstances that maintains separate widget dictionaries per session.
    """
    
    def __init__(self):
        self._current_session_id = None
        self._default_instances = weakref.WeakValueDictionary()
        # Map widget ID to session ID
        self._widget_to_session = {}
        # Per-session storage for widget instances
        self._session_instances = {}
        
    def set_current_session(self, session_id):
        """Set the current session ID for subsequent operations."""
        self._current_session_id = session_id
        if session_id and session_id not in self._session_instances:
            self._session_instances[session_id] = weakref.WeakValueDictionary()
    
    def _get_current_dict(self):
        """Get the runtime instances dict for the current session."""
        if self._current_session_id and self._current_session_id in self._session_instances:
            return self._session_instances[self._current_session_id]
        return self._default_instances
    
    def _get_dict_by_widget_id(self, widget_id):
        """Get the runtime instances dict for a specific widget ID."""
        # First try to find which session owns this widget.
        if widget_id in self._widget_to_session:
            session_id = self._widget_to_session[widget_id]
            if session_id in self._session_instances:
                log.debug(f"_get_dict_by_widget_id({widget_id}): Found in mapping -> session {session_id}")
                return self._session_instances[session_id]
        
        # If not found in mapping, search all session dictionaries.
        for session_id, session_dict in self._session_instances.items():
            if widget_id in session_dict:
                # Update mapping for faster future lookups.
                self._widget_to_session[widget_id] = session_id
                log.debug(f"_get_dict_by_widget_id({widget_id}): Found by search in session {session_id}")
                return session_dict
        
        # Fall back to default if still not found.
        if widget_id in self._default_instances:
            log.debug(f"_get_dict_by_widget_id({widget_id}): Found in default instances")
            return self._default_instances
        
        # Last resort: use current session dict (widget will be created there).
        log.debug(f"_get_dict_by_widget_id({widget_id}): Not found anywhere, using current session")
        return self._get_current_dict()
    
    def __getitem__(self, key):
        # When accessing by key (widget lookup), use widget-to-session mapping.
        log.debug(f"__getitem__({key}): widget_to_session has {len(self._widget_to_session)} entries, "
                  f"session_instances has {len(self._session_instances)} sessions, "
                  f"current_session_id={self._current_session_id}")
        
        result_dict = self._get_dict_by_widget_id(key)
        log.debug(f"__getitem__({key}): Found in dict with {len(result_dict)} widgets")
        
        return result_dict[key]
    
    def __setitem__(self, key, value):
        # When setting, use current session and remember the mapping.
        log.debug(f"__setitem__({key}, {type(value).__name__}): current_session_id={self._current_session_id}")
        if self._current_session_id:
            self._widget_to_session[key] = self._current_session_id
        self._get_current_dict()[key] = value
    
    def __delitem__(self, key):
        # Clean up mapping when widget is deleted
        if key in self._widget_to_session:
            del self._widget_to_session[key]
        del self._get_current_dict()[key]
    
    def __contains__(self, key):
        return key in self._get_dict_by_widget_id(key)
    
    def get(self, key, default=None):
        try:
            return self._get_dict_by_widget_id(key).get(key, default)
        except:
            return default
    
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
            # Try multiple ways to get a unique session ID
            session_id = None
            
            # Method 1: Use client_address if available
            if hasattr(self, 'client_address'):
                session_id = f"{self.client_address[0]}:{self.client_address[1]}"
            
            # Method 2: Use path as part of session (so /say gets different session than /)
            if hasattr(self, 'path'):
                path_part = self.path if self.path != '/' else 'root'
                if session_id:
                    session_id = f"{session_id}_{path_part}"
                else:
                    session_id = path_part
            
            if session_id:
                _session_aware_instances.set_current_session(session_id)
                log.debug(f"Set session ID: {session_id}")
        except Exception as e:
            log.warning(f"Could not set session from client: {e}")


def start(app_class, **kwargs):
    """
    Start the REMI server with multi-path support.
    
    Use this instead of remi.start() to get multi-path functionality.
    
    Args:
        app_class: Your App class (should inherit from remi_multipath.App)
        **kwargs: All arguments that remi.start() accepts
    """
    return remi_start(app_class, **kwargs)

