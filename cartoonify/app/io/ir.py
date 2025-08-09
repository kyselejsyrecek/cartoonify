import evdev
from app.debugging.logging import getLogger
import signal
import time

from app.workflow.multiprocessing import ProcessInterface


BUTTON_IMMEDIATE_TRIGGER = [ 0x7fbfffff, 0xcab11f  ]
BUTTON_2S_TRIGGER = [ 0x7effffff ]
BUTTON_TOGGLE_RECORDING = [ 0xcab142 ]
BUTTON_WINK = [ 0xcab143 ]


def noop():
    pass


class IrReceiver(ProcessInterface):
    """
    interface to IR receiver
    """

    def __init__(self, log=None):
        self._log = log or getLogger(self.__class__.__name__)

        self.dev = None
        self.trigger_callback = noop
        self.trigger_2s_callback = noop
        self.recording_callback = noop
        self.wink_callback = noop


    @staticmethod
    def hook_up(event_service, log, *args, **kwargs):
        ir_receiver = IrReceiver(log)
        ir_receiver.setup(trigger_callback=event_service.capture,
                            trigger_2s_callback = event_service.delayed_capture,
                            recording_callback=event_service.toggle_recording,
                            wink_callback=event_service.wink)
        ir_receiver.start()
    

    def setup(self, trigger_callback=None, trigger_2s_callback = None, recording_callback=None, wink_callback=None):
        """Set the IR receiver interface up and initiate scanning.
        """
        if trigger_callback:
            self.trigger_callback = trigger_callback
        if trigger_2s_callback:
            self.trigger_2s_callback = trigger_2s_callback
        if recording_callback:
            self.recording_callback = recording_callback
        if wink_callback:
            self.wink_callback = wink_callback
        self.dev = self.get_ir_device()
        # Attempt to do a nasty fix of the blocking read which blocks interrupt.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.siginterrupt(signal.SIGINT, True)


    def close(self): # FIXME Unused, not functional.
        print("Closing dev.")
        if self.dev is not None:
            self.dev.close()
            print("Dev closed.")
        print("End of close().")


    def get_ir_device(self):
        """Get evdev.InputDevice corresponding to an IR receiver device if any.
        """
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            if (device.name == "gpio_ir_recv"):
                self._log.info(f'Using IR device {device.path}.')
                return device
        self._log.warning('No IR device found!')


    def start(self):
        """Worker thread.
        """
        self._processing_loop()
        

    def _processing_loop(self):
        """Main processing loop for IR commands (synchronous)"""
        self._log.info('Starting IR receiver processing loop...')
        
        cmd = None
        while True:
            try:
                for event in self.dev.read():
                    self._log.debug(f'Received IR command: 0x{event.value:08x}')
                    if cmd is None:
                        cmd = event.value
                    else:
                        if event.value == 0:
                            if cmd is not None and cmd > 0:
                                self._log.debug('Received terminating IR string. Processing command.')
                                if cmd in BUTTON_IMMEDIATE_TRIGGER:
                                    self._log.debug('Invoking immediate trigger.')
                                    self.trigger_callback()
                                elif cmd in BUTTON_2S_TRIGGER:
                                    self._log.debug('Invoking 2-second trigger.')
                                    self.trigger_2s_callback()
                                elif cmd in BUTTON_TOGGLE_RECORDING:
                                    self._log.debug('Toggling recording.')
                                    self.recording_callback()
                                elif cmd in BUTTON_WINK:
                                    self._log.debug('Invoking wink trigger.')
                                    self.wink_callback()
                                else:
                                    self._log.debug('Unknown IR command, ignoring.')
                                cmd = None
                        else:
                            self._log.debug('Received unsupported multi-integer command. Ignoring.')
                            cmd = -1
                time.sleep(0.1)  # Small delay to prevent busy waiting
                        
            except Exception as e:
                self._log.exception(f'Error in IR processing: {e}')
                time.sleep(1)  # Wait before retrying