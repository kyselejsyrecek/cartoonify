from __future__ import division
import png
import numpy as np
from pathlib import Path
import logging
from csv import writer
from tempfile import NamedTemporaryFile
import os
import time

from app.sketch import SketchGizeh
from app.gpio import Gpio
from app.utils.attributedict import AttributeDict
from app.debugging import profiling


class Workflow(object):
    """controls execution of app
    """

    def __init__(self, dataset, imageprocessor, camera, config):
        self._config = AttributeDict({
            "annotate": False,
            "threshold": 0.3,
            "max_overlapping": 0.5,
            "max_objects": None,
            "min_inference_dimension": 300,
            "max_inference_dimension": 1024,
            "fit_width": None,
            "fit_height": None,
            "max_image_number": 10000
        })
        self._config.update(config)
        self._path = Path('')
        self._image_path = Path('')
        self._dataset = dataset
        self._image_processor = imageprocessor
        self._sketcher = None
        self._cam = camera
        self._gpio = Gpio()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._image = None
        self._annotated_image = None
        self._image_labels = []
        self._boxes = None
        self._classes = None
        self._scores = None
        self._image_number = 0
        self._original_image_number = -1

    def setup(self, setup_gpio=True):
        if setup_gpio:
            self._logger.info('setting up GPIO...')
            self._gpio.setup(trigger_release_callback=self.capture_event, trigger_held_callback=self.print_previous_original)
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
        image_numbers = sorted(list(map(lambda x: int(os.path.basename(x).split('image')[1].split('.')[0]), self._path.glob('image?*.jpg'))))
        self._image_number = image_numbers[-1] + 1 if len(image_numbers) > 0 else 0
        self._original_image_number = self._image_number - 1
        if self._cam is not None:
            capture_config = self._cam.create_still_configuration()
            # TODO resolution = (640, 480)
            self._cam.configure(capture_config)
            self._cam.start()
            time.sleep(2) # FIXME Replace with lazy sleep instead? Is that even needed?
        self._gpio.set_initial_state()
        self._logger.info('setup finished.')


    def capture_event(self, e):
        """Capture a photo, convert it to cartoon and then print it if possible.
        """
        print('capture button pressed.')
        self.run(print_cartoon=True)


    def print_previous_original(self, e):
        """Print previous original. 
           When called multiple times, prints originals in backward order.
        """
        if self._original_image_number <= 0:
            self._logger.info(f'Refusing to print previous original as no previous photo is available. Original image number: {self._original_image_number}.')
        else:
            print('printing original photo.')
            path = self._path / ('image' + str(self._original_image_number) + '.jpg')
            self._gpio.print(str(path))
            self._original_image_number = self._original_image_number - 1


    def run(self, print_cartoon=False): # TODO Refactor. This code must be unified.
        """capture an image, process it, save to file, and optionally print it

        :return:
        """
        try:
            self._logger.info('capturing and processing image.')
            self._gpio.set_busy()
            self.increment()
            path = self._path / ('image' + str(self._image_number) + '.jpg')
            self.capture(path)
            self.process(path)
            annotated, cartoon = self.save_results()
            if print_cartoon:
                self._gpio.print(str(cartoon))
        except Exception as e:
            self._logger.exception(e)

        self._gpio.set_ready()

    def capture(self, path):
        if self._cam is not None:
            self._logger.info('capturing image')
            self._cam.capture_file(str(path))
            self._gpio.blink_eyes()
        else:
            raise AttributeError("app wasn't started with --camera flag, so you can't use the camera to capture images.")
        return path

    def process(self, image_path, threshold=None, max_objects=None):
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
        cartoon_path = self._image_path.with_name('cartoon' + str(self._image_number) + '.png')
        labels_path = self._image_path.with_name('labels' + str(self._image_number) + '.txt')
        with open(str(labels_path), 'w') as f:
            f.write(','.join(self.image_labels))
        if debug:
            scores_path = self._image_path.with_name('scores' + str(self._image_number) + '.txt')
            with open(str(scores_path), 'w') as f:
                fcsv = writer(f)
                fcsv.writerow(map(str, self._scores.flatten()))
        if self._config.annotate:
            self._save_3d_numpy_array_as_png(self._annotated_image, annotated_path)
        self._sketcher.save_png(cartoon_path)
        return annotated_path, cartoon_path

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
        if self._cam is not None:
            self._cam.close()
        self._image_processor.close()
        self._gpio.close()

    def increment(self):
        self._image_number = (self._image_number + 1) % self._config.max_image_number
        self._original_image_number = self._image_number - 1

    @property
    def image_labels(self):
        return self._image_labels
