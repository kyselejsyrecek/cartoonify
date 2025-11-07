from app.debugging.logging import getLogger, suppress_stderr, restore_stderr
from piclap import *
from threading import Thread
from app.workflow.multiprocessing import ProcessInterface
import os
import sys


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
        self._log.debug('Invoking immediate trigger.')
        self.trigger_callback()

    def on3Claps(self):
        """Custom action for 3 claps."""
        self._log.debug('Invoking 2-second trigger.')
        self.trigger_2s_callback()

    def on4Claps(self):
        """Custom action for 4 claps."""
        self._log.debug('Invoking wink trigger.')
        self.wink_callback()


class ClapDetector(ProcessInterface):
    """
    Interface to clap detector.
    """

    def __init__(self, log=None, exit_event=None, halt_event=None):
        self._log = log or getLogger(self.__class__.__name__)
        self._exit_event = exit_event
        self._halt_event = halt_event
        self._available = False
        self.listener = None
        self.config = None
        self.thread = None
        self.trigger_callback = noop
        self.trigger_2s_callback = noop
        self.wink_callback = noop


    @staticmethod
    def hook_up(event_service, log, exit_event, halt_event, *args, **kwargs):
        clap_detector = ClapDetector(log, exit_event, halt_event)
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
        
        # Check if audio input device is available before initializing
        if not self._check_audio_input_available():
            self._log.info('No audio input device available - clap detector disabled.')
            self._available = False
            return
        
        self.config = Config(trigger_callback, trigger_2s_callback, wink_callback)
        try:
            # Suppress interactive input by setting calibrate=False and using default settings.
            self.listener = Listener(config=self.config, calibrate=False)
            self._available = True
            self._log.info('Clap detector initialized successfully.')
        except (EOFError, KeyboardInterrupt) as e:
            self._log.warning('Clap detector initialization failed - no interactive input available.')
            self.listener = None
            self._available = False
        except Exception as e:
            self._log.warning(f'Clap detector initialization failed: {e}')
            self.listener = None
            self._available = False

    def _check_audio_input_available(self):
        """Check if any audio input device is available by testing PyAudio initialization.
        
        Suppresses ALSA error messages during check by redirecting file descriptor 2 (stderr).
        Works even when sys.stderr is already redirected to a custom object.
        
        :return: True if audio input is available, False otherwise
        """
        try:
            import pyaudio
            
            # Temporarily redirect stderr to suppress ALSA errors.
            # ALSA writes directly to FD 2, not through Python's sys.stderr object.
            suppress_stderr()
            
            try:
                p = pyaudio.PyAudio()
                # Check for at least one input device.
                has_input = False
                for i in range(p.get_device_count()):
                    dev_info = p.get_device_info_by_index(i)
                    if dev_info.get('maxInputChannels', 0) > 0:
                        has_input = True
                        break
                p.terminate()
                return has_input
            finally:
                # Restore stderr.
                restore_stderr()
        except Exception as e:
            self._log.error(f'Error checking audio input availability: {e}')
            return False

    def start(self):
        """Start worker thread."""
        if not self._available:
            self._log.info('Clap detector not available - skipping detection.')
            return
        
        self._processing_loop()

    def _processing_loop(self):
        """Main processing loop for clap detection (synchronous)."""
        if not self._available:
            self._log.warning('Cannot start clap detection - not available.')
            return
            
        self._log.info('Starting clap detector processing loop...')
        
        try:
            self._log.debug('Worker thread of clap detector started.')
            self.listener.start()
            self._log.debug('Worker thread of clap detector terminated.')
        except Exception as e:
            self._log.exception(f'Clap detector processing failed: {e}')