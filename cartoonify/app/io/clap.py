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
        """Custom action for 2 claps.
        """
        self._logger.debug('Invoking immediate trigger.')
        self.trigger_callback()

    def on3Claps(self):
        """Custom action for 3 claps.
        """
        self._logger.debug('Invoking 2-second trigger.')
        self.trigger_2s_callback()

    def on4Claps(self):
        """Custom action for 3 claps.
        """
        self._logger.debug('Invoking wink trigger.')
        self.wink_callback()


class ClapDetector:
    """
    interface to IR receiver
    """

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.listener = None
        self.config = None
        self.thread = None
        self.trigger_callback = noop
        self.trigger_2s_callback = noop
        self.wink_callback = noop

    
    def setup(self, trigger_callback=None, trigger_2s_callback=None, wink_callback=None):
        """Set the clap detector interface up and initiate detection.
        """
        if trigger_callback:
            self.trigger_callback = trigger_callback
        if trigger_2s_callback:
            self.trigger_2s_callback = trigger_2s_callback
        if wink_callback:
            self.wink_callback = wink_callback
        self.config = Config(trigger_callback, trigger_2s_callback, wink_callback)
        self.listener = Listener(config=self.config, calibrate=False)
        self.thread = Thread(target = self._worker)
        self.thread.start()


    def _worker(self):
        """Worker thread.
        """
        self._logger.debug('Worker thread of clap detector started.')
        self.listener.start()
        self._logger.debug('Worker thread of clap detector terminated.')