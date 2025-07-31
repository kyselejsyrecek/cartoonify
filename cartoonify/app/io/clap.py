import logging
from piclap import *
from threading import Thread


def noop():
    pass


class Config(Settings):
    """Describes custom configurations and action methods to be executed based
    on the number of claps detected.
    """

    def __init__(self, trigger_callback=None, trigger_2s_callback=None, wink_callback=None):
        Settings.__init__(self)
        self.method.value = 10000
        self.trigger_callback = trigger_callback if trigger_callback else noop
        self.trigger_2s_callback = trigger_2s_callback if trigger_2s_callback else noop
        self.wink_callback = wink_callback if wink_callback else noop

    def on2Claps(self):
        """Custom action for 2 claps."""
        self._logger.debug('Invoking immediate trigger.')
        self.trigger_callback()

    def on3Claps(self):
        """Custom action for 3 claps."""
        self._logger.debug('Invoking 2-second trigger.')
        self.trigger_2s_callback()

    def on4Claps(self):
        """Custom action for 4 claps."""
        self._logger.debug('Invoking wink trigger.')
        self.wink_callback()


class ClapDetector:
    """
    Interface to clap detector.
    """

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self.listener = None
        self.config = None
        self.thread = None
        self.trigger_callback = noop
        self.trigger_2s_callback = noop
        self.wink_callback = noop


    @staticmethod
    def hook_up(event_service, logger, *args, **kwargs):
        clap_detector = ClapDetector(logger)
        clap_detector.setup(trigger_callback=event_service.capture,
                            trigger_2s_callback=event_service.delayed_capture,
                            wink_callback=event_service.wink)
        clap_detector.start()


    def setup(self, trigger_callback=None, trigger_2s_callback=None, wink_callback=None):
        """Set the clap detector interface up and initiate detection."""
        if trigger_callback:
            self.trigger_callback = trigger_callback
        if trigger_2s_callback:
            self.trigger_2s_callback = trigger_2s_callback
        if wink_callback:
            self.wink_callback = wink_callback
        self.config = Config(trigger_callback, trigger_2s_callback, wink_callback)
        try:
            # Suppress interactive input by setting calibrate=False and using default settings.
            self.listener = Listener(config=self.config, calibrate=False)
            self._logger.info('Clap detector initialized successfully.')
        except (EOFError, KeyboardInterrupt) as e:
            self._logger.warning('Clap detector initialization failed - no interactive input available.')
            self.listener = None
        except Exception as e:
            self._logger.warning(f'Clap detector initialization failed: {e}')
            self.listener = None

    def start(self):
        """Start worker thread."""
        if self.listener is None:
            self._logger.warning('Clap detector not initialized - skipping detection.')
            return
        
        self._processing_loop()

    def _processing_loop(self):
        """Main processing loop for clap detection (synchronous)."""
        if self.listener is None:
            self._logger.warning('Cannot start clap detection - listener not initialized.')
            return
            
        self._logger.info('Starting clap detector processing loop...')
        
        try:
            self._logger.debug('Worker thread of clap detector started.')
            self.listener.start()
            self._logger.debug('Worker thread of clap detector terminated.')
        except Exception as e:
            self._logger.error(f'Clap detector processing failed: {e}')