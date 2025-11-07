from app.debugging.logging import getLogger

class BaseIODevice:
    """Unified interface for IO devices.

    Provides common enabled/available state management and lifecycle hooks.
    Subclasses should override setup() to perform initialization but call
    super().setup(enabled=...) early to register state. Availability should
    be detected and stored in self._available.
    
    Note: Currently availability is only checked when device is enabled.
    TODO: Check availability even when disabled to allow runtime enabling.
    """
    def __init__(self, enabled: bool = True):
        self._log = getLogger(self.__class__.__name__)
        self._enabled = enabled
        self._available = True  # Assume available until setup verifies.

    # -- State management -------------------------------------------------
    def enable(self):
        """Enable runtime usage (does not (re)initialize hardware)."""
        if not self._enabled:
            self._enabled = True
            self._log.info('Enabled.')

    def disable(self):
        """Disable runtime usage."""
        if self._enabled:
            self._enabled = False
            self._log.info('Disabled.')

    def toggle(self):
        if self._enabled:
            self.disable()
        else:
            self.enable()

    @property
    def is_enabled(self):
        """Check if device is enabled for runtime usage.
        
        :return: True if device is enabled, False otherwise
        """
        return self._enabled

    @is_enabled.setter
    def is_enabled(self, value: bool):
        self._enabled = value

    @property
    def is_available(self):
        """Check if device is available (hardware detected/accessible).
        
        :return: True if device hardware is available, False otherwise
        """
        return self._available

    # -- Lifecycle -------------------------------------------------------
    def setup(self, enabled: bool | None = None):
        """Base setup optionally overrides enabled flag. Subclasses should perform detection.
        
        :param enabled: Optional override of enabled flag before initialization (None keeps current state).
        """
        if enabled is not None:
            self._enabled = enabled
        # Availability left unchanged here; subclass should set _available accordingly.

    def close(self):  # Optional override
        pass
