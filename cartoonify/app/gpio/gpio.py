import importlib
import logging
import re
import time

from subprocess import *


# GPIO PINS
#HALT_BUTTON = 6
CAPTURE_BUTTON = 5
READY_LED = 4
BUSY_LED = 27
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

        self.gpio = None
        self.led_ready = None
        self.led_busy = None
        self.led_printing = None
        self.led_big_eye = None
        self.led_small_eye = None
        self.button_capture = None

        try:
            self.gpio = importlib.import_module('gpiozero')
        except ImportError as e:
            self._logger.exception(e)
            self._logger.info('raspi gpio module not found, continuing...')

    def setup(self, capture_callback=None):
        """setup GPIO pin to trigger callback function when capture pin goes low

        :return:
        """
        if not self.available():
            return
        
        self.led_ready = self.gpio.LED(READY_LED)
        self.led_busy = self.gpio.LED(BUSY_LED)
        self.led_printing = self.gpio.LED(PRINTING_LED)
        self.led_big_eye = self.gpio.LED(EYE_BIG_LED)
        self.led_small_eye = self.gpio.LED(EYE_SMALL_LED)
        self.button_capture = self.gpio.Button(CAPTURE_BUTTON)
        if capture_callback:
            self.button_capture.when_released = capture_callback
        self.set_busy()
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


    def set_busy(self):
        """set status LEDs

        :param bool ready:
        :return:
        """
        if not self.available():
            return
        
        self.led_ready.off()
        self.led_printing.off()
        self.led_busy.on()

    def set_ready(self):
        """set status LEDs

        :param bool ready:
        :return:
        """
        if not self.available():
            return
        
        self.flash_eyes_individually()
        self.led_ready.on()
        self.led_busy.off()
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
        self.led_ready.off()
        
        self.led_printing.off()
        self.led_busy.on()
        time.sleep(0.5)
        self.led_printing.on()
        self.led_busy.off()
        time.sleep(0.5)
        self.led_printing.off()
        self.led_busy.on()
        time.sleep(0.5)
        self.led_printing.on()
        self.led_busy.off()
        time.sleep(0.5)
        self.led_busy.on()
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
        output = check_output(['lp', '-o', 'orientation-requested=5', '-o', 'fit-to-page', '-c', image_file])
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

    def get_capture_pin(self):
        """get state of capture pin

        :return:
        """
        if not self.available():
            return False
        
        return self.button_capture.is_pressed

    def available(self):
        """return true if gpio package is available

        :return:
        """
        return self.gpio is not None

    def close(self):
        if self.available():
          self.led_ready.close()
          self.led_busy.close()
          self.led_printing.close()
          self.led_big_eye.close()
          self.led_small_eye.close()
          self.button_capture.close()