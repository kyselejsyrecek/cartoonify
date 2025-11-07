from __future__ import division
import concurrent.futures
import importlib
import logging
import multiprocessing
import numpy as np
import png
import os
import signal
import sys
import time
from csv import writer
from libcamera import controls
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from app.sketch import SketchGizeh
from app.io import Gpio, IrReceiver, ClapDetector, SoundPlayer, Camera, Accelerometer, Printer
from app.utils.attributedict import AttributeDict
from app.debugging import profiling
from app.debugging.logging import getLogger  # Import our enhanced getLogger
from app.workflow.multiprocessing import *
from app.utils.asynctask import AsyncExecutor, async_task, exclusive


def signal_handler(signum, frame):
    log = getLogger(__name__)
    if exit_event.is_set():
        return  # Already exiting, return immediately.
    log.info(f"Parent Process: Received signal {signum}, signaling children to exit.")
    exit_event.set() # Set the event to signal all processes to exit.
    #workflow._terminate()


class Workflow(AsyncExecutor):
    """controls execution of app
    """

    def __init__(self, dataset, imageprocessor, config, i18n=None):
        self._config = AttributeDict({
            "annotate": False,
            "threshold": 0.3,
            "max_overlapping": 0.5,
            "max_objects": None,
            "min_inference_dimension": 300,
            "max_inference_dimension": 1024,
            "fit_width": None,
            "fit_height": None,
            "max_image_number": 10000,
            "fast_init": False,
            "camera": False,
            "rotate_180deg": False,
            "no_camera": False,
            "no_clap_detector": False,
            "no_ir_receiver": False,
            "audio_backend": None,
            "video_format": "h264",
            "video_resolution": "1080p", 
            "video_fps": 30,
            "video_raw_stream": False,
            "volume": 1.0,
            "no_accelerometer": False,
            "no_printer": False,
            "no_gpio": False,
            "alsa_numid": 4,
            "tts_language": "cs",
            "sound_theme": "default",
            "raspi_headless": False,
            "ip": "0.0.0.0",
            "port": 8081,
            "no_sound": False,
            "cert_file": None,
            "key_file": None
        })
        self._log = getLogger(self.__class__.__name__)  # Use enhanced getLogger
        self._config.update(config)
        self._i18n = i18n

        # Initialize the AsyncExecutor (ThreadPoolExecutor)
        # We discard any operations requested when another operation is in progress.
        # However, to make that possible at least 2 worker threads are required by current solution.
        # Initialize executor with named lock registry. 'event' lock coordinates event handlers.
        self._event_lock = Lock()
        AsyncExecutor.__init__(self, max_workers=2, logger=self._log, locks={'event': self._event_lock})

        self._path = Path('')
        self._image_path = Path('')
        self._event_manager_address = ('127.0.0.1', 50000)
        self._event_manager_authkey = b'489r4gs/r2*!-B.u'
        self._dataset = dataset
        self._image_processor = imageprocessor
        self._camera = Camera(enabled=self._config.camera and not self._config.no_camera)
        self._gpio = Gpio(enabled=not self._config.no_gpio or self._config.raspi_headless or self._config.gui or self._config.web_server)
        self._printer = Printer(enabled=not self._config.no_printer)
        self._ir_receiver = None
        self._clap_detector = None
        self._sound = SoundPlayer(enabled=not self._config.no_sound)
        self._sketcher = None
        self._web_gui = None
        self._image = None
        self._annotated_image = None
        self._image_labels = []
        self._boxes = None
        self._classes = None
        self._scores = None
        self._next_image_number = 0
        self._last_original_image_number = -1
        self._is_recording = False
        self._is_initialized = False

        # Register this instance as the event handler service.
        # All public methods (including task_wait/task_result/...) will be accessible via proxy.
        EventManager.register('event_service', callable=lambda: self)
        # Proces manager has to register its own objects. Instantiate it before EventManager is started.
        self._process_manager = ProcessManager(self._event_manager_address, self._event_manager_authkey)
        self._is_initialized = True


    def _terminate(self):
        """Terminate all resources safely. Can be called multiple times."""
        if not self._is_initialized:
            return  # Not fully initialized yet, nothing to terminate
            
        self._is_initialized = False  # Mark as no longer initialized
        self._log.info('Starting workflow termination...')
        
        try:
            # Terminate process manager and child processes
            if hasattr(self, '_process_manager') and self._process_manager:
                self._process_manager.terminate()
        except Exception as e:
            self._log.exception(f'Error terminating process manager: {e}')

        try:
            # Terminate the event manager process using the static method
            EventManager.terminate()
        except Exception as e:
            self._log.exception(f'Error terminating event manager process: {e}')
        
        self._log.info('Workflow termination completed.')

    def close(self):
        try:
            if self._camera:
                self._camera.close()
        except Exception as e:
            self._log.exception(f'Error closing camera: {e}')

        try:
            if self._image_processor:
                self._image_processor.close()
        except Exception as e:
            self._log.exception(f'Error closing image processor: {e}')

        try:
            if self._gpio:
                self._gpio.close()
        except Exception as e:
            self._log.exception(f'Error closing GPIO: {e}')
        
        try:
            if self._sound:
                self._sound.close()
        except Exception as e:
            self._log.exception(f'Error closing sound: {e}')
        
        #if not self._config.no_ir_receiver:
        #    self._ir_receiver.close()
        
        self._terminate()


    def __del__(self):
        try:
            # Shut down the AsyncExecutor worker thread.
            self.shutdown()
        except Exception as e:
            # Log error if logger is available, otherwise just ignore
            if hasattr(self, '_log') and self._log:
                self._log.exception(f'Error shutting down async executor: {e}')
        
        # Free resources
        # TODO self.close()?
        self._terminate()


    def setup(self):
        # Set up the SIGINT handler for the parent process
        signal.signal(signal.SIGINT, signal_handler)

        # Initialize and start event manager using static method
        EventManager.start(self._event_manager_address, self._event_manager_authkey)

        try:
            # TODO aplay -D plughw:CARD=Device,DEV=0 -t raw -c 1 -r 22050 -f S16_LE /tmp/file.pcm
            if self._gpio.is_enabled:
                self._log.info('setting up GPIO...')
                self._gpio.setup(fast_init=self._config.fast_init,
                                trigger_release_callback=self.capture,
                                trigger_held_callback=self.print_previous_original,
                                approach_callback=self.someone_approached,
                                halt_callback=self.system_halt)
                if not self._config.no_ir_receiver:
                    self._ir_receiver = self._process_manager.start_process(IrReceiver)
                if not self._config.no_clap_detector:
                    self._clap_detector = self._process_manager.start_process(ClapDetector)
                if not self._config.no_accelerometer:
                    self._accelerometer = self._process_manager.start_process(Accelerometer)
                self._log.info('done')
            
            # Start web GUI if requested
            if self._config.gui or self._config.web_server:
                from app.gui import WebGui
                
                if self._config.gui:
                    self._log.info('Starting GUI...')
                    print('Starting GUI...')
                elif self._config.web_server:
                    self._log.info(f'Starting HTTP server on address {self._config.ip}:{self._config.port}...')
                
                self._web_gui = self._process_manager.start_process(
                    WebGui, 
                    self._i18n,  # i18n object from run.py
                    self._config.raspi_headless,  # cam_only mode - limits GUI features to camera operations only
                    self._config.ip, 
                    self._config.port,
                    self._config.gui,  # start_browser - True for GUI mode, False for web_server mode
                    self._config.cert_file,  # SSL certificate file
                    self._config.key_file,   # SSL private key file
                    capture_stdout=False,  # Allow WebGUI stdout to go to console
                    capture_stderr=False,  # Allow WebGUI stderr to go to console
                    filter_ansi=False      # Don't filter ANSI codes from WebGUI
                )
                
                if self._config.gui:
                    self._log.info('GUI started successfully')
                elif self._config.web_server:
                    self._log.info('HTTP server started successfully')
                    print(f'HTTP server running on address {self._config.ip}:{self._config.port}.')
            
            # Setup camera system
            if self._camera.is_enabled:
                self._log.info('setting up camera...')
                self._camera.setup(
                    rotate_180deg=self._config.rotate_180deg,
                    video_format=self._config.video_format,
                    video_resolution=self._config.video_resolution,
                    video_fps=self._config.video_fps,
                    video_raw_stream=self._config.video_raw_stream
                )
                self._log.info('done')
            
            # Setup sound system
            self._log.info('setting up sound system...')
            self._sound.setup(audio_backend=self._config.audio_backend,
                volume=self._config.volume,
                alsa_numid=self._config.alsa_numid,
                tts_language=self._config.tts_language,
                theme=self._config.sound_theme)
            # Configure printer availability.
            self._printer.setup()
            self._log.info('done')
            self._log.info('loading cartoon dataset...')
            self._dataset.setup()
            self._log.info('Done')
            self._sketcher = SketchGizeh()
            self._sketcher.setup()
            self._log.info('loading tensorflow model...')
            self._image_processor.setup()
            self._log.info('Done')
            self._path = Path(__file__).parent / '..' / '..' / 'images'
            if not self._path.exists():
                self._path.mkdir()
            # The number of cartoon*.png files should be greater than or equal to that of image*.jpg files.
            # Cartoons originate also from other sources than just the camera (which is what produces image*.jpg files).
            image_numbers = sorted(list(map(lambda x: int(os.path.basename(x).split('cartoon')[1].split('.')[0]), self._path.glob('cartoon?*.png'))))
            self._next_image_number = image_numbers[-1] + 1 if len(image_numbers) > 0 else 0
            self._last_original_image_number = self._next_image_number - 1
            self._set_initial_state()
            self._log.info('setup finished.')
        except Exception as e:
            self._log.exception(f'Error intializing interfaces: {e}') 
            self.close()
            raise e

    def _execute_concurrent_tasks(self, *tasks):
        """Execute multiple tasks concurrently and wait for completion
        
        :param tasks: Functions to execute concurrently
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            # Submit all tasks
            futures = [executor.submit(task) for task in tasks]
            
            # Wait for all to complete
            concurrent.futures.wait(futures)


    def run(self, print_cartoon=False): # TODO Refactor. This code must be unified.
        """capture an image, process it, save to file, and optionally print it

        :return:
        """
        try:
            self._log.info('capturing and processing image.')
            original = self._capture()
            self.process()
            annotated, cartoon, image_labels = self.save_results()
            if print_cartoon:
                self._print_image(cartoon)
        except Exception as e:
            self._log.exception(e)
        
        self.increment()
        self._gpio.set_ready()
        if self._web_gui:
            self._web_gui.show_image(original, annotated, cartoon, image_labels)

    def _capture(self, path=None):
        if not self._camera.is_enabled:
            raise AttributeError("App wasn't started with --camera flag, so you can't use the camera to capture images.")
        if path is None:
            path = self._path / ('image' + str(self._next_image_number) + '.jpg')
        self._log.info('capturing image')
        self._camera.capture_file(str(path))
        self._gpio.blink_eyes()
        return path

    def process(self, image_path=None, threshold=None, max_objects=None):
        """processes an image. If no path supplied, then capture from camera

        :param float threshold: threshold for object detection (0.0 to 1.0)
        :param max_objects: If not none, draw N objects with highest confidency at most
        :param path: directory to save results to
        :param bool camera_enabled: whether to use raspi camera or not
        :param image_path: image to process, if camera is disabled
        :return:
        """
        self._log.info('processing image...')

        if threshold is None:
            threshold = self._config.threshold
        if max_objects is None:
            max_objects = self._config.max_objects
        if image_path is None:
            image_path = self._path / ('image' + str(self._next_image_number) + '.jpg')

        try:
            self._image_path = Path(image_path)
            raw_image = self._image_processor.load_image_raw(image_path)
            image = self._image_processor.load_image_into_numpy_array(raw_image, fit_width=self._config.fit_width, fit_height=self._config.fit_height)
            # load a scaled version of the image into memory
            inference_scale = min(self._config.min_inference_dimension, self._config.max_inference_dimension / max(raw_image.size))
            raw_inference_image = self._image_processor.load_image_raw(image_path)
            inference_image = self._image_processor.load_image_into_numpy_array(raw_inference_image, scale=inference_scale)
            profiling.evaluation_point("input image loaded")
            self._boxes, self._scores, self._classes = self._image_processor.detect(inference_image, self._config.max_overlapping)
            profiling.evaluation_point("detection done")
            # annotate the original image
            if self._config.annotate:
                self._annotated_image = self._image_processor.annotate_image(image, self._boxes, self._classes, self._scores, threshold=threshold)
                profiling.evaluation_point("annotation done")
            self._sketcher = SketchGizeh()
            self._sketcher.setup(image.shape[1], image.shape[0])
            if max_objects:
                sorted_scores = sorted(self._scores.flatten())
                threshold = sorted_scores[-min([max_objects, self._scores.size])]
            self._image_labels = self._sketcher.draw_object_recognition_results(self._boxes,
                                 self._classes.astype(np.int32),
                                 self._scores,
                                 self._image_processor.labels,
                                 self._dataset,
                                 threshold=threshold)
        except (ValueError, IOError) as e:
            self._log.exception(e)

    def save_results(self, debug=False):
        """save result images as png and list of detected objects as txt
        if debug is true, save a list of all detected objects and their scores

        :return tuple: (path to annotated image, path to cartoon image)
        """
        self._log.info('saving results...')
        annotated_path = self._image_path.parent / (self._image_path.name + '.annotated.png')
        cartoon_path = self._image_path.with_name('cartoon' + str(self._next_image_number) + '.png')
        labels_path = self._image_path.with_name('labels' + str(self._next_image_number) + '.txt')
        with open(str(labels_path), 'w') as f:
            f.write(','.join(self._image_labels))
        if debug:
            scores_path = self._image_path.with_name('scores' + str(self._next_image_number) + '.txt')
            with open(str(scores_path), 'w') as f:
                fcsv = writer(f)
                fcsv.writerow(map(str, self._scores.flatten()))
        if self._config.annotate:
            self._save_3d_numpy_array_as_png(self._annotated_image, annotated_path)
        self._sketcher.save_png(cartoon_path)
        return annotated_path, cartoon_path, self._image_labels

    def _save_3d_numpy_array_as_png(self, image, path):
        """saves a NxNx3 8 bit numpy array as a png image

        :param image: N.N.3 numpy array
        :param path: path to save image to, e.g. './image/image.png
        :return:
        """
        if len(image.shape) != 3 or image.dtype is not np.dtype('uint8'):
            raise TypeError('image must be NxNx3 array')
        with NamedTemporaryFile(dir=os.path.dirname(str(path)), delete=False) as f:
            writer = png.Writer(image.shape[1], image.shape[0], greyscale=False, bitdepth=8)
            writer.write(f, np.reshape(image, (-1, image.shape[1] * image.shape[2])))
        os.replace(f.name, str(path))

    def increment(self):
        self._next_image_number = (self._next_image_number + 1) % self._config.max_image_number
        self._last_original_image_number = self._next_image_number - 1

    def _print_image(self, image_path):
        """Print image with busy LED indication and wait for completion if job submitted."""
        if self._gpio.is_available:
            self._gpio.led_busy.on()
        lp_out = self._printer.print_image(str(image_path))
        if lp_out:
            self._printer.wait(lp_out)
        if self._gpio.is_available:
            self._gpio.led_busy.off()

    def _print_text(self, text):
        """Print plain text (no LED state changes here)."""
        lp_out = self._printer.print_text(text)
        if lp_out:
            self._printer.wait(lp_out)

    @async_task
    @exclusive('event', blocking=True)
    def _set_initial_state(self):
        """Set initial state for GPIO and play awake sound simultaneously"""
        self._log.info('Setting initial state...')
        self._execute_concurrent_tasks(
            self._sound.fx.awake,
            self._gpio.set_initial_state
        )
        self._log.info('Initial state set.')

    # Event handlers
    @async_task
    @exclusive('event', blocking=True)
    def system_halt(self, e=None):
        """Handle system halt button press
        
        :param Button e: Originator of the event (gpiozero object).
        """
        self._log.info('System halt button pressed - waiting for current operation to finish...')
        self._log.info('Initiating system shutdown.')
        # Set halt event to signal shutdown
        halt_event.set()
        # Set exit event to exit all sub-processes
        exit_event.set()
        # Block the event thread until the main thread stops the process.
        time.sleep(5)


    @async_task
    @exclusive('event')
    def capture(self, e=None):
        """Capture a photo, convert it to cartoon and then print it if possible.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from WebGUI.
        """
        self._log.info('Capture button pressed.')
        self._execute_concurrent_tasks(
            self._sound.fx.capture,
            lambda: self.run(print_cartoon=True)
        )


    @async_task
    @exclusive('event')
    def delayed_capture(self, e=None):
        """Capture a photo after 2 seconds, convert it to cartoon and then print it if possible.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from IrReceiver.
        """
        self._log.info('Button for delayed capture pressed.')
        self._gpio.set_recording_state(not self._is_recording)
        time.sleep(0.2)
        self._gpio.set_recording_state(self._is_recording)
        time.sleep(0.8)
        self._gpio.set_recording_state(not self._is_recording)
        time.sleep(0.2)
        self._gpio.set_recording_state(self._is_recording)
        time.sleep(0.8)
        self._execute_concurrent_tasks(
            self._sound.fx.capture,
            lambda: self.run(print_cartoon=True)
        )


    @async_task
    @exclusive('event')
    def print_previous_original(self, e=None):
        """Print previous original. 
           When called multiple times, prints originals in backward order.
        """
        start_num = self._last_original_image_number
        if self._last_original_image_number <= 0:
            self._log.info(f'Refusing to print previous original as no previous photo is available. Original image number: {self._last_original_image_number}.')
        else:
            self._log.info('Capture button held - printing original photo.')
            while True:
                path = self._path / ('image' + str(self._last_original_image_number) + '.jpg')
                if Path(path).is_file():
                    break
                else:
                    # Not all cartoons must have originated from a camera capture.  We could create symlinks
                    # when images from non-standard paths are processed but that would bring its own drawbacks.
                    # For now, skip photos that do not exist.
                    self._last_original_image_number = (self._last_original_image_number - 1) % self._next_image_number
                    if self._last_original_image_number == start_num:
                        self._log.info('No original photo found.')
                        return

            self._execute_concurrent_tasks(
                self._sound.fx.capture,
                lambda: self._print_image(path)
            )
            self._last_original_image_number = (self._last_original_image_number - 1) % self._next_image_number


    @async_task
    @exclusive('event')
    def toggle_recording(self, e=None):
        """Toggle video recording.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from IrReceiver.
        """
        self._log.info('Button toggling video recording pressed.')
        self._is_recording = not self._is_recording
        self._gpio.set_recording_state(self._is_recording)
        if self._camera is not None:
            if self._is_recording:
                self._camera.start_recording()
            else:
                self._camera.stop_recording()


    @async_task
    @exclusive('event')
    def wink(self, e=None):
        """Wink the bigger eye.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from IrReceiver.
        """
        self._log.info('Wink button pressed.')
        self._gpio.wink()

    
    @async_task
    @exclusive('event')
    def someone_approached(self, e=None):
        """React to detected proximity of an object.

        :param DigitalInputDevice e: Originator of the event (gpiozero object).
        """
        self._log.info('Someone approached.')
        self._execute_concurrent_tasks(
            self._sound.fx.greeting,
            self._gpio.blink_eyes
        )

    @async_task
    @exclusive('event')
    def dizzy(self, e=None):
        """Handle dizzy motion detection event
        
        :param e: Originator of the event
        """
        self._log.info('Motion detected - triggering dizzy response.')
        self._execute_concurrent_tasks(
            self._sound.fx.dizzy,
            self._gpio.blink_eyes
        )

    @async_task
    @exclusive('event')
    def say(self, text):
        """Speak text using text-to-speech
        
        :param text: Text to speak
        """
        self._log.info(f'TTS requested: "{text}"')
        self._sound.say(text)

    def get_exit_event(self):
        """Access to global exit_event for child processes."""
        return exit_event
 
    def get_halt_event(self):
        """Access to global halt_event for child processes."""
        return halt_event
