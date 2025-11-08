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

# Monkey-patch REMI's do_GET to set session context from widget ID lookup
_original_do_GET = server.App.do_GET if hasattr(server.App, 'do_GET') else None

def _patched_do_GET(self):
    """Patched do_GET that sets session context before handling request."""
    # Try to extract widget ID from path and set session accordingly.
    # Path format: /WIDGET_ID/method_name
    try:
        path_parts = self.path.split('/')
        if len(path_parts) >= 2:
            potential_widget_id = path_parts[1].split('?')[0]
            # If this looks like a widget ID (numeric string), try to find its session.
            if potential_widget_id.isdigit():
                if potential_widget_id in _session_aware_instances._widget_to_session:
                    session_id = _session_aware_instances._widget_to_session[potential_widget_id]
                    _session_aware_instances.set_current_session(session_id)
                    log.debug(f"do_GET: Set session to {session_id} for widget {potential_widget_id}")
    except Exception as e:
        log.warning(f"do_GET: Failed to extract session from path: {e}")
    
    if _original_do_GET:
        return _original_do_GET(self)

if _original_do_GET:
    server.App.do_GET = _patched_do_GET


class App(RemiApp):
    """
    Extended REMI App that supports multiple URL paths with separate sessions.
    
    Use this class instead of remi.App to get multi-path support.
    Each browser tab/window gets its own session with separate widget instances.
    """
    
    def __init__(self, *args, **kwargs):
        # Use the App instance ID as session ID - each App instance is one session.
        # This works because REMI creates one App instance per browser tab/connection.
        self._session_id = str(id(self))
        _session_aware_instances.set_current_session(self._session_id)
        log.debug(f"App.__init__: Set session ID to {self._session_id}")
        
        super(App, self).__init__(*args, **kwargs)
        
        # After parent init, we can access path and add it to session tracking.
        if hasattr(self, 'path'):
            log.debug(f"App.__init__: Session {self._session_id} is for path {self.path}")
    
    def execute_javascript(self, *args, **kwargs):
        """Override to set session context before executing JavaScript."""
        _session_aware_instances.set_current_session(self._session_id)
        return super(App, self).execute_javascript(*args, **kwargs)
    
    def _process_all(self):
        """Override to set session context before processing updates."""
        _session_aware_instances.set_current_session(self._session_id)
        return super(App, self)._process_all()


def start(app_class, **kwargs):
    """
    Start the REMI server with multi-path support.
    
    Use this instead of remi.start() to get multi-path functionality.
    
    Args:
        app_class: Your App class (should inherit from remi_multipath.App)
        **kwargs: All arguments that remi.start() accepts
    """
    return remi_start(app_class, **kwargs)

