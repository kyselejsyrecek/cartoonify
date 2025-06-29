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
from app.io import Gpio, IrReceiver, ClapDetector, PlaySound, Camera, Accelerometer
from app.utils.attributedict import AttributeDict
from app.debugging import profiling
from app.workflow.multiprocessing import *
from app.utils.asynctask import *


def signal_handler(signum, frame):
    print(f"Parent Process: Received signal {signum}, signaling children to exit.")
    exit_event.set() # Set the event to signal all processes to exit
    #workflow.terminate()


class Workflow(object):
    """controls execution of app
    """

    def __init__(self, dataset, imageprocessor, config):
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
            "clap_detector": False,
            "no_ir_sensor": False,
            "audio_backend": None,
            "video_format": "h264",
            "video_resolution": "1080p", 
            "video_fps": 30,
            "volume": 1.0,
            "no_accelerometer": False,
            "alsa_numid": 4,
        })
        self._lock = Lock()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._config.update(config)

        # Initialize the AsyncExecutor decorator.
        # We discard any operations requested when another operation is in progress.
        # However, to make that possible at least 2 worker threads are required by current solution.
        self._async_executor = AsyncExecutor(max_workers=2)

        self._path = Path('')
        self._image_path = Path('')
        self._event_manager_address = ('127.0.0.1', 50000)
        self._event_manager_authkey = b'489r4gs/r2*!-B.u'
        self._event_manager = None
        self._event_manager_server = None
        self._event_manager_process = None
        self._dataset = dataset
        self._image_processor = imageprocessor
        self._camera = Camera() if self._config.camera else None
        self._gpio = Gpio()
        self._ir_receiver = None
        self._clap_detector = None
        self._sound = PlaySound()
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

        # Register this instance as the event handler service.
        EventManager.register('event_service', callable=lambda: self)
        self._process_manager = ProcessManager(self._event_manager_address, self._event_manager_authkey)


    def terminate(self):
        print("Workflow terminate().") # FIXME Remove.
        self._process_manager.terminate()

        # Terminate the manager process
        if self._event_manager_process.is_alive():
            self._logger.debug('Terminating event manager...')
            self._event_manager_process.terminate()
            self._event_manager_process.join(timeout=1)
            if self._event_manager_process.is_alive():
                self._logger.warning(f"Manager process {self._event_manager_process.pid} did not terminate gracefully, killing.")
                os.kill(self._event_manager_process.pid, signal.SIGKILL)
        
        #if not self._config.no_ir_receiver:
        #    self._ir_receiver.close()
        print("Workflow terminate() end.") # FIXME Remove.


    def __del__(self):
        print("Workflow __del__().")
        # Shut down the asynchronous task pool.
        self._async_executor.shutdown()


    def setup(self, setup_gpio=True):
        # Set up the SIGINT handler for the parent process
        signal.signal(signal.SIGINT, signal_handler)

        # Initialize event manager
        self._event_manager = EventManager(self._event_manager_address, self._event_manager_authkey)
        self._event_manager_server = self._event_manager.get_server()
        # Start the manager server in a separate process
        # This prevents the parent's main loop from being blocked by the manager.
        self._event_manager_process = multiprocessing.Process(target=self._event_manager_server.serve_forever)
        self._event_manager_process.daemon = True # Ensures the manager process terminates with the parent
        self._event_manager_process.start()

        # TODO aplay -D plughw:CARD=Device,DEV=0 -t raw -c 1 -r 22050 -f S16_LE /tmp/file.pcm
        if setup_gpio:
            self._logger.info('setting up GPIO...')
            self._gpio.setup(fast_init=self._config.fast_init,
                             trigger_release_callback=self.capture,
                             trigger_held_callback=self.print_previous_original,
                             approach_callback=self.someone_approached,
                             halt_callback=self.system_halt)
            if not self._config.no_ir_receiver:
                self._ir_receiver = self._process_manager.start_process(IrReceiver.hook_up)
            if not self._config.no_clap_detector:
                self._clap_detector = self._process_manager.start_process(ClapDetector.hook_up)
            if not self._config.no_accelerometer:
                self._accelerometer = self._process_manager.start_process(Accelerometer.hook_up)
            self._logger.info('done')
        
        # Setup camera system
        if self._camera is not None:
            self._logger.info('setting up camera...')
            self._camera.setup(
                rotate_180deg=self._config.rotate_180deg,
                video_format=self._config.video_format,
                video_resolution=self._config.video_resolution,
                video_fps=self._config.video_fps
            )
            self._logger.info('done')
        
        # Setup sound system
        self._logger.info('setting up sound system...')
        self._sound.setup(audio_backend=self._config.audio_backend, volume=self._config.volume, alsa_numid=self._config.alsa_numid)
        self._logger.info('done')
        self._logger.info('loading cartoon dataset...')
        self._dataset.setup()
        self._logger.info('Done')
        self._sketcher = SketchGizeh()
        self._sketcher.setup()
        self._logger.info('loading tensorflow model...')
        self._image_processor.setup()
        self._logger.info('Done')
        self._path = Path(__file__).parent / '..' / '..' / 'images'
        if not self._path.exists():
            self._path.mkdir()
        # The number of cartoon*.png files should be greater than or equal to that of image*.jpg files.
        # Cartoons originate also from other sources than just the camera (which is what produces image*.jpg files).
        image_numbers = sorted(list(map(lambda x: int(os.path.basename(x).split('cartoon')[1].split('.')[0]), self._path.glob('cartoon?*.png'))))
        self._next_image_number = image_numbers[-1] + 1 if len(image_numbers) > 0 else 0
        self._last_original_image_number = self._next_image_number - 1
        self._set_initial_state()
        self._logger.info('setup finished.')

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
            self._logger.info('capturing and processing image.')
            original = self._capture()
            self.process()
            annotated, cartoon, image_labels = self.save_results()
            if print_cartoon:
                self._gpio.print(str(cartoon))
        except Exception as e:
            self._logger.exception(e)
        
        self.increment()
        self._gpio.set_ready()
        if self._web_gui:
            self._web_gui.show_image(original, annotated, cartoon, image_labels)

    def _capture(self, path=None):
        if self._camera is not None:
            if path is None:
                path = self._path / ('image' + str(self._next_image_number) + '.jpg')
            self._logger.info('capturing image')
            self._camera.capture_file(str(path))
            self._gpio.blink_eyes()
        else:
            raise AttributeError("app wasn't started with --camera flag, so you can't use the camera to capture images.")
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
        self._logger.info('processing image...')

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
            self._logger.exception(e)

    def save_results(self, debug=False):
        """save result images as png and list of detected objects as txt
        if debug is true, save a list of all detected objects and their scores

        :return tuple: (path to annotated image, path to cartoon image)
        """
        self._logger.info('saving results...')
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

    def close(self):
        if self._camera is not None:
            # Ensure video recording is stopped before closing
            if self._is_recording:
                self._camera.stop_recording()
            self._camera.close()
        self._image_processor.close()
        self._gpio.close()
        self._sound.close()

    def increment(self):
        self._next_image_number = (self._next_image_number + 1) % self._config.max_image_number
        self._last_original_image_number = self._next_image_number - 1

    def _set_initial_state(self):
        """Set initial state for GPIO and play awake sound simultaneously"""
        if not self._lock.acquire(blocking=True):
            self._logger.error('Error setting initial state.')
            self.close()
        try:
            self._logger.info('Setting initial state...')
            # Run both operations concurrently
            self._execute_concurrent_tasks(
                self._gpio.set_initial_state,
                self._sound.awake
            )
            self._logger.info('Initial state set.')
        finally:
            self._lock.release()

    def connect_web_gui(self, web_gui):
        # Must be hooked up later since Web GUI requires GPIO to be already initialized.
        self._web_gui = web_gui

    # Event handlers
    @async_task
    def system_halt(self, e=None):
        """Handle system halt button press
        
        :param Button e: Originator of the event (gpiozero object).
        """
        self._logger.info('System halt button pressed - waiting for current operation to finish...')
        # Wait for any current operation to finish (blocking acquire)
        self._lock.acquire()
        try:
            self._logger.info('Initiating system shutdown.')
            # Set exit event to signal all processes to stop
            exit_event.set()
            # Close all resources
            self.close()
            # Wait a moment before shutdown
            time.sleep(2)
            # Exit with special code 42 for shutdown
            sys.exit(42)
        finally:
            self._lock.release()


    @async_task
    def capture(self, e=None):
        """Capture a photo, convert it to cartoon and then print it if possible.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from WebGUI.
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Capture event ignored because another operation is in progress.')
            return
        try:
            self._logger.info('Capture button pressed.')
            self.run(print_cartoon=True)
        finally:
            self._lock.release()


    @async_task
    def delayed_capture(self, e=None):
        """Capture a photo after 2 seconds, convert it to cartoon and then print it if possible.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from IrReceiver.
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Delayed capture event ignored because another operation is in progress.')
            return
        try:
            self._logger.info('Button for delayed capture pressed.')
            self._gpio.set_recording_state(not self._is_recording)
            time.sleep(0.2)
            self._gpio.set_recording_state(self._is_recording)
            time.sleep(0.8)
            self._gpio.set_recording_state(not self._is_recording)
            time.sleep(0.2)
            self._gpio.set_recording_state(self._is_recording)
            time.sleep(0.8)
            self.run(print_cartoon=True)
        finally:
            self._lock.release()


    @async_task
    def print_previous_original(self, e=None):
        """Print previous original. 
           When called multiple times, prints originals in backward order.
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Not printing previous original because another operation is in progress.')
            return
        try:
            start_num = self._last_original_image_number
            if self._last_original_image_number <= 0:
                self._logger.info(f'Refusing to print previous original as no previous photo is available. Original image number: {self._last_original_image_number}.')
            else:
                self._logger.info('Capture button held - printing original photo.')
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
                            self._logger.info('No original photo found.')
                            return

                self._gpio.print(str(path))
                self._last_original_image_number = (self._last_original_image_number - 1) % self._next_image_number
        finally:
            self._lock.release()


    @async_task
    def toggle_recording(self, e=None):
        """Toggle video recording.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from IrReceiver.
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Event toggle recording ignored because another operation is in progress.')
            return
        try:
            self._logger.info('Button toggling video recording pressed.')
            self._is_recording = not self._is_recording
            self._gpio.set_recording_state(self._is_recording)
            
            if self._camera is not None:
                if self._is_recording:
                    self._camera.start_recording()
                else:
                    self._camera.stop_recording()
        finally:
            self._lock.release()


    @async_task
    def wink(self, e=None):
        """Wink the bigger eye.

        :param SmartButton e: Originator of the event (gpiozero object). None if called from IrReceiver.
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Event wink ignored because another operation is in progress.')
            return
        try:
            self._logger.info('Wink button pressed.')
            self._gpio.wink()
        finally:
            self._lock.release()

    
    @async_task
    def someone_approached(self, e=None):
        """React to detected proximity of an object.

        :param DigitalInputDevice e: Originator of the event (gpiozero object).
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Approach event ignored because another operation is in progress.')
            return
        try:
            self._logger.info('Someone approached.')
            self._gpio.blink_eyes()
        finally:
            self._lock.release()

    @async_task
    def dizzy(self, e=None):
        """Handle dizzy motion detection event
        
        :param e: Originator of the event
        """
        if not self._lock.acquire(blocking=False):
            self._logger.info('Dizzy motion event ignored because another operation is in progress.')
            return
        try:
            self._logger.info('Motion detected - triggering dizzy response.')
            # Execute dizzy sound and eye blink concurrently
            self._execute_concurrent_tasks(
                self._sound.dizzy,
                self._gpio.blink_eyes
            )
        finally:
            self._lock.release()
