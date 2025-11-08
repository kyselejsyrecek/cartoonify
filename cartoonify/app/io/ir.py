import evdev
import os
from pathlib import Path
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

    def __init__(self, log=None, exit_event=None, halt_event=None, debounce_time=0.25):
        self._log = log or getLogger(self.__class__.__name__)
        self._exit_event = exit_event
        self._halt_event = halt_event
        self._debounce_time = debounce_time

        self.dev = None
        self._rc_path = None
        self.trigger_callback = noop
        self.trigger_2s_callback = noop
        self.recording_callback = noop
        self.wink_callback = noop


    @staticmethod
    def hook_up(event_service, log, exit_event, halt_event, *args, **kwargs):
        debounce_time = kwargs.get('debounce_time', 0.25)
        ir_receiver = IrReceiver(log, exit_event, halt_event, debounce_time)
        ir_receiver.setup(trigger_callback=event_service.capture,
                            trigger_2s_callback = event_service.delayed_capture,
                            recording_callback=event_service.toggle_recording,
                            wink_callback=event_service.wink)
        ir_receiver.start()
    

    def setup(self, trigger_callback=None, trigger_2s_callback=None, recording_callback=None, wink_callback=None, protocols=None):
        """Set the IR receiver interface up and initiate scanning.
        
        :param trigger_callback: Callback for immediate trigger events
        :param trigger_2s_callback: Callback for 2-second delayed trigger events
        :param recording_callback: Callback for recording toggle events
        :param wink_callback: Callback for wink events
        :param protocols: List of IR protocols to enable (e.g., ['nec', 'rc-5']). If None, all protocols are enabled.
        """
        if trigger_callback:
            self.trigger_callback = trigger_callback
        if trigger_2s_callback:
            self.trigger_2s_callback = trigger_2s_callback
        if recording_callback:
            self.recording_callback = recording_callback
        if wink_callback:
            self.wink_callback = wink_callback
        self.dev = self._find_and_initialize_ir_device(protocols)
        # Attempt to do a nasty fix of the blocking read which blocks interrupt.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.siginterrupt(signal.SIGINT, True)


    def close(self):
        """Close the IR device and disable all IR protocols."""
        self._log.debug("Closing IR receiver.")
        
        # Disable all IR protocols before closing.
        if self._rc_path:
            self._disable_all_protocols()
        
        if self.dev is not None:
            self.dev.close()
            self._log.debug("IR device closed.")
        
        self._log.debug("End of close().")


    def _find_and_initialize_ir_device(self, protocols=None):
        """Find IR device and initialize protocols.
        
        :param protocols: List of IR protocols to enable. If None, all protocols are enabled.
        :return: evdev.InputDevice object or None
        """
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            if (device.name == "gpio_ir_recv"):
                self._log.info(f'Using IR device {device.path}.')
                self._initialize_ir_protocols(device, protocols)
                return device
        self._log.warning('No IR device found!')


    def _initialize_ir_protocols(self, device, protocols=None):
        """Initialize IR protocols via sysfs interface.
        
        This enables the kernel IR decoder to decode signals from the receiver.
        Without this, evdev won't receive any events even though the device is opened.
        
        :param device: evdev.InputDevice object
        :param protocols: List of IR protocols to enable (e.g., ['nec', 'rc-5']). If None, all protocols are enabled.
        """
        try:
            # Find the rc device corresponding to this input device.
            # Input devices are in /sys/class/input/eventX
            # RC devices are in /sys/class/rc/rcY
            sysfs_path = Path(device.path).resolve()
            self._log.debug(f'Device path: {sysfs_path}')
            
            # Navigate from /dev/input/eventX to /sys/class/input/eventX
            event_name = sysfs_path.name  # e.g., "event1"
            input_class_path = Path(f'/sys/class/input/{event_name}')
            
            if not input_class_path.exists():
                self._log.warning(f'Could not find sysfs path: {input_class_path}')
                return
            
            # Find the parent device (usually under device/rc/)
            # The structure is typically: /sys/class/input/eventX/device -> ../../devices/.../rcY/input/eventX
            device_link = input_class_path / 'device'
            if device_link.exists():
                real_device = device_link.resolve()
                self._log.debug(f'Real device path: {real_device}')
                
                # Look for rc device in parent hierarchy.
                # Usually: /sys/devices/platform/ir-receiver@12/rc/rc0
                for parent in real_device.parents:
                    rc_dirs = list(parent.glob('rc/rc*'))
                    if rc_dirs:
                        rc_path = rc_dirs[0]
                        self._log.debug(f'Found RC device: {rc_path}')
                        self._rc_path = rc_path
                        self._configure_protocols(protocols)
                        return
            
            self._log.warning('Could not find RC device in sysfs hierarchy.')
            
        except Exception as e:
            self._log.exception(f'Failed to initialize IR protocols via sysfs: {e}')


    def _configure_protocols(self, protocols=None):
        """Configure IR protocols for the RC device via sysfs.
        
        :param protocols: List of protocol names to enable (e.g., ['nec', 'rc-5']). If None, all available protocols are enabled.
        """
        if not self._rc_path:
            self._log.warning('No RC device path available.')
            return
        
        protocols_file = self._rc_path / 'protocols'
        
        if not protocols_file.exists():
            self._log.warning(f'Protocols file not found: {protocols_file}')
            return
        
        try:
            # Read available protocols (format: "[nec] [rc-5] rc-6 [sony] ..." where [...] means enabled).
            with open(protocols_file, 'r') as f:
                current = f.read().strip()
            self._log.debug(f'Current IR protocols: {current}')
            
            available = current.replace('[', '').replace(']', '').split()
            
            # Determine which protocols to enable.
            if protocols is None:
                # Enable all available protocols.
                protocols_to_enable = available
            else:
                # Enable only specified protocols that are available.
                protocols_to_enable = [p for p in protocols if p in available]
                if len(protocols_to_enable) < len(protocols):
                    missing = set(protocols) - set(protocols_to_enable)
                    self._log.warning(f'Requested protocols not available: {missing}')
            
            if not protocols_to_enable:
                self._log.error('No protocols to enable.')
                return
            
            # Write protocols with + prefix to enable them.
            protocols_str = ' '.join([f'+{p}' for p in protocols_to_enable])
            
            self._log.debug(f'Enabling IR protocols: {protocols_to_enable}')
            with open(protocols_file, 'w') as f:
                f.write(protocols_str)
            
            # Verify and log enabled protocols.
            with open(protocols_file, 'r') as f:
                new_protocols = f.read().strip()
            
            # Extract enabled protocols from the result (those in brackets).
            enabled = [p.strip('[]') for p in new_protocols.split() if p.startswith('[')]
            self._log.info(f'IR protocols enabled: {enabled}')
            
        except PermissionError:
            self._log.error(f'Permission denied writing to {protocols_file}. Run as root or configure udev rules.')
        except Exception as e:
            self._log.exception(f'Failed to configure IR protocols: {e}')


    def _disable_all_protocols(self):
        """Disable all IR protocols."""
        if not self._rc_path:
            return
        
        protocols_file = self._rc_path / 'protocols'
        
        try:
            self._log.debug('Disabling all IR protocols.')
            
            # Read current protocols to get list of all available protocols.
            with open(protocols_file, 'r') as f:
                current = f.read().strip()
            
            available = current.replace('[', '').replace(']', '').split()
            disable_str = ' '.join([f'-{p}' for p in available if p])
            
            with open(protocols_file, 'w') as f:
                f.write(disable_str)
            
            self._log.debug('All IR protocols disabled.')
            
        except PermissionError:
            self._log.error(f'Permission denied writing to {protocols_file}.')
        except Exception as e:
            self._log.exception(f'Failed to disable IR protocols: {e}')


    def start(self):
        """Worker thread."""
        try:
            self._processing_loop()
        finally:
            self.close()
            self._log.info('IR receiver stopped.')
        

    def _processing_loop(self):
        """Main processing loop for IR commands (synchronous)."""
        self._log.info('Starting IR receiver processing loop...')
        
        cmd = None
        last_command_time = 0
        
        while not self._exit_event.is_set():
            try:
                for event in self.dev.read():
                    self._log.debug(f'Received IR command: 0x{event.value:08x}')
                    if cmd is None:
                        cmd = event.value
                    else:
                        if event.value == 0:
                            if cmd > 0:
                                # Check debounce time.
                                current_time = time.time()
                                if current_time - last_command_time < self._debounce_time:
                                    self._log.debug(f'Ignoring command due to debounce (time since last: {current_time - last_command_time:.3f}s).')
                                    cmd = None
                                    continue
                                last_command_time = current_time
                                
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

            except BlockingIOError:
                #self._log.debug('No IR commands received.')
                time.sleep(0.05) # Safety interval between polling cycles.

            except Exception as e:
                self._log.exception(f'Error in IR processing: {e}')
                time.sleep(0.5) # Wait before retrying after error.
        
        self._log.info('Stopping IR receiver...')