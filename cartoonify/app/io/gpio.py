import importlib
import logging
import re
import time

from subprocess import *
import atexit


# GPIO PINS
#HALT_BUTTON = 6
CAPTURE_BUTTON = 5
ALIVE_LED = 4
RECORDING_LED = 27
PRINTING_LED = 17

EYE_BIG_LED = 18
EYE_SMALL_LED = 22


class Gpio:
    """
    interface to raspi GPIO
    """

    def __init__(self):
        self._status_pin = 2
        self._logger = logging.getLogger(self.__class__.__name__)

        # References to imported libraries
        self.gpio = None
        self.elements = None

        # State objects
        self.initialized = False
        self.led_alive = None
        self.led_recording = None
        self.led_printing = None
        self.led_big_eye = None
        self.led_small_eye = None
        self.button_capture = None

        try:
            self.gpio = importlib.import_module('gpiozero')
            self.elements = importlib.import_module('app.io.elements')
        except (ImportError, ModuleNotFoundError) as e:
            self._logger.exception(e)
            self._logger.info('raspi gpio module not found, continuing...')

    def __del__(self):
        if not self.available():
            return

        # Revert power LED back to its initial state which signals that the app is not running (heartbeat pattern).
        try:
            self.led_alive.off()
        except:
            pass
        call(['sudo', 'sh', '-c', 'echo heartbeat > /sys/class/leds/power_led/trigger'])

    def setup(self, trigger_release_callback=None, trigger_held_callback=None, trigger_hold_time=1.5):
        """setup GPIO pin to trigger callback function when capture pin goes low

        :return:
        """
        if self.gpio is None:
            return
            
        # Hook-up all objects.
        atexit.register(self.__del__)
        self.led_alive = self.gpio.LED(ALIVE_LED)
        self.led_recording = self.gpio.LED(RECORDING_LED)
        self.led_printing = self.gpio.LED(PRINTING_LED)
        self.led_big_eye = self.gpio.LED(EYE_BIG_LED)
        self.led_small_eye = self.gpio.LED(EYE_SMALL_LED)
        self.button_capture = self.elements.SmartButton(CAPTURE_BUTTON, hold_time=trigger_hold_time, bounce_time=0.1)
        if trigger_release_callback:
            self.button_capture.when_released = trigger_release_callback
        if trigger_held_callback:
            self.button_capture.when_held = trigger_held_callback

        # Initial state
        # The LED is connected to two GPIO pins. Disable heartbeat blinking so that the LED is not overpowered.
        call(['sudo', 'sh', '-c', 'echo none > /sys/class/leds/power_led/trigger && echo 0 > /sys/class/leds/power_led/brightness'])
        self.initialized = True
        # Set power LED state.
        self.led_alive.on()
        # Just in case.
        self.led_recording.off()
        self.led_printing.off()
        self.led_big_eye.off()
        self.led_small_eye.off()

        # Awakening animation
        time.sleep(4)
        self.led_small_eye.on()
        time.sleep(2)
        self.led_small_eye.off()
        time.sleep(4)
        self.led_small_eye.on()
        time.sleep(6)
        self.led_small_eye.off()
        time.sleep(3)
        self.led_small_eye.on()
        time.sleep(0.1)
        self.led_small_eye.off()
        time.sleep(0.1)
        self.led_small_eye.on()
        time.sleep(0.1)
        self.led_small_eye.off()
        time.sleep(0.5)
        self.led_small_eye.on()


    def set_ready(self):
        """set status LEDs

        :param bool ready:
        :return:
        """
        if not self.available():
            return
        
        self.flash_eyes_individually()
        self.led_printing.off()

    def set_initial_state(self):

        self.set_ready()
        time.sleep(3)
        self.blink_eyes()


    def flash_eyes_individually(self):
        """Flash the eye LEDs in a pattern
        """
        if not self.available():
            return
        
        self.led_big_eye.off()
        self.led_small_eye.off()
        time.sleep(0.5)
        self.led_big_eye.on()
        time.sleep(0.3)
        self.led_big_eye.off()
        self.led_small_eye.on()
        time.sleep(0.3)
        self.led_big_eye.on()
        self.led_small_eye.off()
        time.sleep(0.3)
        self.led_big_eye.off()
        self.led_small_eye.on()
        time.sleep(0.3)
        self.led_big_eye.off()
        self.led_small_eye.off()
        time.sleep(0.5)
        self.led_big_eye.on()
        self.led_small_eye.on()


    def blink_eyes(self):
        """Flash the eye LEDs in a pattern
        """
        if not self.available():
            return

        self.led_big_eye.off()
        self.led_small_eye.off()
        time.sleep(0.1)
        self.led_big_eye.on()
        self.led_small_eye.on()
        time.sleep(0.1)
        self.led_big_eye.off()
        self.led_small_eye.off()
        time.sleep(0.1)
        self.led_big_eye.on()
        self.led_small_eye.on()


    def set_error_state(self, error_msg):
        self.led_printing.off()

        # The "recordng" LED is red, wink, wink ;-).
        self.led_recording.on()
        time.sleep(0.5)
        self.led_printing.on()
        self.led_recording.off()
        time.sleep(0.5)
        self.led_printing.off()
        self.led_recording.on()
        time.sleep(0.5)
        self.led_printing.on()
        self.led_recording.off()
        time.sleep(0.5)
        self.led_recording.on()
        self.led_printing.on()
        time.sleep(2)
        
        if e != "":
            process = Popen(['lp', '-o', 'cpi=13'], stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, err = process.communicate(error_msg)
            self._wait_for_print_job(output)
        
        self.set_ready()


    def print(self, image_file):
        """Print the image (and text).
        """
        if not self.available():
            return
        
        self.led_printing.on()
        # Media dimensions come from width of printable area (for 58mm paper) and cartoon width
        # which appears as height of the print when printed in landscape orientation.
        output = check_output(['lp', '-o', 'orientation-requested=5', '-o', 'media=Custom.57.86x102.87mm', '-o', 'fit-to-page', image_file])
        self._wait_for_print_job(output)
        self.led_printing.off()
    

    def _wait_for_print_job(self, lp_output):
        """Waits until the given print job is finished.
        """
        job_id = re.search('request id is (.*) \\(.*', str(lp_output)).group(1)
        while True:
            result = run(['lpstat'], stdout=PIPE, stderr=PIPE, text=True)
            if not re.match(f'^{job_id}', result.stdout):
                break
            time.sleep(1)

    def available(self):
        """return true if gpio package is available

        :return:
        """
        return self.gpio is not None and self.initialized

    def close(self):
        if self.available():
          self.led_alive.close()
          self.led_recording.close()
          self.led_printing.close()
          self.led_big_eye.close()
          self.led_small_eye.close()
          self.button_capture.close()
          self.initialized = False