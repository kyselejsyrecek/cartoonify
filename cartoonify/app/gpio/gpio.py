import importlib
import logging
import time


# GPIO PINS
HALT_BUTTON = 6
CAPTURE_BUTTON = 5
READY_LED = 4
BUSY_LED = 27
PRINTING_LED = 17

EYE_1_LED = 18
EYE_2_LED = 22


class Gpio:
    """
    interface to raspi GPIO
    """

    def __init__(self):
        self._status_pin = 2
        self._logger = logging.getLogger(self.__class__.__name__)
        self.gpio = None
        try:
            self.gpio = importlib.import_module('RPi.GPIO')
        except ImportError as e:
            self._logger.exception(e)
            self._logger.info('raspi gpio module not found, continuing...')

    def setup(self, capture_callback=None):
        """setup GPIO pin to trigger callback function when capture pin goes low

        :return:
        """
        if not self.available():
            return
        
        self.gpio.setmode(self.gpio.BCM)
        self.gpio.setup(READY_LED, self.gpio.OUT)
        self.gpio.setup(BUSY_LED, self.gpio.OUT)
        self.gpio.setup(PRINTING_LED, self.gpio.OUT)
        self.gpio.setup(EYE_1_LED, self.gpio.OUT)
        self.gpio.setup(EYE_2_LED, self.gpio.OUT)
        self.gpio.setup(HALT_BUTTON, self.gpio.IN, pull_up_down=self.gpio.PUD_UP)
        self.gpio.setup(CAPTURE_BUTTON, self.gpio.IN, pull_up_down=self.gpio.PUD_UP)
        if capture_callback:
            self.gpio.add_event_detect(CAPTURE_BUTTON, self.gpio.FALLING, callback=capture_callback, bouncetime=200)
        self.set_busy()

    def set_busy(self):
        """set status LEDs

        :param bool ready:
        :return:
        """
        if not self.available():
            return
        
        self.gpio.output(READY_LED, self.gpio.LOW)
        self.gpio.output(BUSY_LED, self.gpio.HIGH)
        self.gpio.output(PRINTING_LED, self.gpio.HIGH)

    def set_ready(self):
        """set status LEDs

        :param bool ready:
        :return:
        """
        if not self.available():
            return
        
        self.flash_eyes()
        self.gpio.output(READY_LED, self.gpio.HIGH)
        self.gpio.output(BUSY_LED, self.gpio.LOW)
        self.gpio.output(PRINTING_LED, self.gpio.LOW)


    def flash_eyes(self):
        """Flash the eye LEDs in a pattern
        """
        if not self.available():
            return
        
        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.LOW)
        time.sleep(0.5)
        self.gpio.output(EYE_1_LED, self.gpio.HIGH)
        time.sleep(0.3)
        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.HIGH)
        time.sleep(0.3)
        self.gpio.output(EYE_1_LED, self.gpio.HIGH)
        self.gpio.output(EYE_2_LED, self.gpio.LOW)
        time.sleep(0.3)
        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.HIGH)
        time.sleep(0.3)
        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.LOW)
        time.sleep(0.5)
        self.gpio.output(EYE_1_LED, self.gpio.HIGH)
        self.gpio.output(EYE_2_LED, self.gpio.HIGH)


    def blink_eyes(self):
        """Flash the eye LEDs in a pattern
        """
        if not self.available():
            return

        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.LOW)
        time.sleep(0.1)
        self.gpio.output(EYE_1_LED, self.gpio.HIGH)
        self.gpio.output(EYE_2_LED, self.gpio.HIGH)
        time.sleep(0.1)
        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.LOW)
        time.sleep(0.1)
        self.gpio.output(EYE_1_LED, self.gpio.HIGH)
        self.gpio.output(EYE_2_LED, self.gpio.HIGH)


    def shutdown(self): # FIXME This is dead code. There already is a shutdown service!
        """Shut down the Pi safely.
        """
        self.gpio.output(READY_LED, self.gpio.LOW)
        self.gpio.output(BUSY_LED, self.gpio.HIGH)
        self.gpio.output(PRINTING_LED, self.gpio.HIGH)
        self.gpio.output(EYE_1_LED, self.gpio.LOW)
        self.gpio.output(EYE_2_LED, self.gpio.LOW)
        os.system("sudo halt")


    def set_error_state(self, e):
        self.gpio.output(READY_LED, self.gpio.LOW)
        
        self.gpio.output(PRINTING_LED, self.gpio.LOW)
        self.gpio.output(BUSY_LED, self.gpio.HIGH)
        time.sleep(0.5)
        self.gpio.output(PRINTING_LED, self.gpio.HIGH)
        self.gpio.output(BUSY_LED, self.gpio.LOW)
        time.sleep(0.5)
        self.gpio.output(PRINTING_LED, self.gpio.LOW)
        self.gpio.output(BUSY_LED, self.gpio.HIGH)
        time.sleep(0.5)
        self.gpio.output(PRINTING_LED, self.gpio.HIGH)
        self.gpio.output(BUSY_LED, self.gpio.LOW)
        time.sleep(0.5)
        self.gpio.output(BUSY_LED, self.gpio.HIGH)
        self.gpio.output(PRINTING_LED, self.gpio.HIGH)
        time.sleep(2)
        
        #if e != "":
        #    printer.println(e) # TODO printer
        #    printer.feed(2)
        
        self.gpio.output(PRINTING_LED, self.gpio.LOW)
        self.gpio.output(BUSY_LED, self.gpio.LOW)


    def print(self, image_file):
        """Print the image (and text).
        """
        if not self.available():
            return
        
        self.gpio.output(READY_LED, self.gpio.LOW)
        self.gpio.output(BUSY_LED, self.gpio.HIGH)
        
        self.gpio.output(BUSY_LED, self.gpio.LOW)
        self.gpio.output(PRINTING_LED, self.gpio.HIGH)
        
        # try:
        #     img = Image.open(image_file) # TODO from PIL import Image
        # except:
        #     showErrorState("ERROR: No image found")
        #     return
        # 
        # # MAX CHARS: 32 "12345678901234567890123456789012"
        # printer.println("SPRING FOR ZINES!  April 8, 2018") # TODO printer = Adafruit_Thermal("/dev/ttyUSB0", 9600, timeout=5)
        # printer.println("--------------------------------")
        # 
        # printer.printImage(img)
        # 
        # printer.println("VOMIT COMIC #" + str(num))
        # printer.println("www.cadinbatrack.com/vomit-comic")
        # printer.feed(3)
        
        self.set_ready()

    def get_capture_pin(self):
        """get state of capture pin

        :return:
        """
        if not self.available():
            return False
        
        return self.gpio.input(CAPTURE_BUTTON) == self.gpio.LOW

    def available(self):
        """return true if gpio package is available

        :return:
        """
        return self.gpio is not None

    def close(self):
        if self.available():
            self.gpio.cleanup()
