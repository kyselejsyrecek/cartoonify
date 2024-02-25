from __future__ import division
import png
import numpy as np
from pathlib import Path
import logging
from app.sketch import SketchGizeh
from app.gpio import Gpio
import subprocess
from csv import writer


class Workflow(object):
    """controls execution of app
    """

    def __init__(self, dataset, imageprocessor, camera, annotate = False,
                 threshold=0.3, max_objects=None,
                 min_inference_dimension=300, max_inference_dimension=1024,
                 fit_width=None, fit_height=None):
        self._path = Path('')
        self._image_path = Path('')
        self._dataset = dataset
        self._image_processor = imageprocessor
        self._sketcher = None
        self.gpio = Gpio()
        self._cam = camera
        self._annotate = annotate
        self._threshold = threshold
        self._max_objects = max_objects
        self._min_inference_dimension = min_inference_dimension
        self._max_inference_dimension = max_inference_dimension
        self._fit_width = fit_width
        self._fit_height = fit_height
        self._logger = logging.getLogger(self.__class__.__name__)
        self._image = None
        self._annotated_image = None
        self._image_labels = []
        self._boxes = None
        self._classes = None
        self._scores = None
        self.count = 0

    def setup(self, setup_gpio=True):
        self._logger.info('loading cartoon dataset...')
        self._dataset.setup()
        self._logger.info('Done')
        self._sketcher = SketchGizeh()
        self._sketcher.setup()
        self._logger.info('loading tensorflow model...')
        self._image_processor.setup()
        self._logger.info('Done')
        if setup_gpio:
            self._logger.info('setting up GPIO...')
            self.gpio.setup(capture_callback=self.run)
            self._logger.info('done')
        self._path = Path(__file__).parent / '..' / '..' / 'images'
        if not self._path.exists():
            self._path.mkdir()
        self.count = len(list(self._path.glob('image*.jpg')))
        if self._cam is not None:
            self._cam.resolution = (640, 480)
        self._logger.info('setup finished.')

    def run(self, print_cartoon=False):
        """capture an image, process it, save to file, and optionally print it

        :return:
        """
        try:
            self._logger.info('capturing and processing image.')
            self.gpio.set_status_pin(True)
            self.count += 1
            path = self._path / ('image' + str(self.count) + '.jpg')
            self.capture(path)
            self.process(path)
            annotated, cartoon = self.save_results()
            if print_cartoon:
                subprocess.call(['lp', '-o', 'landscape', '-c', str(cartoon)])
            self.gpio.set_status_pin(False)
        except Exception as e:
            self._logger.exception(e)

    def capture(self, path):
        if self._cam is not None:
            self._logger.info('capturing image')
            self._cam.capture(str(path))
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
            threshold = self._threshold
        if max_objects is None:
            max_objects = self._max_objects

        try:
            self._image_path = Path(image_path)
            raw_image = self._image_processor.load_image_raw(image_path)
            image = self._image_processor.load_image_into_numpy_array(raw_image, fit_width=self._fit_width, fit_height=self._fit_height)
            # load a scaled version of the image into memory
            inference_scale = min(self._min_inference_dimension, self._max_inference_dimension / max(raw_image.size))
            raw_inference_image = self._image_processor.load_image_raw(image_path)
            inference_image = self._image_processor.load_image_into_numpy_array(raw_inference_image, scale=inference_scale)
            self._boxes, self._scores, self._classes, num = self._image_processor.detect(inference_image)
            # annotate the original image
            if self._annotate:
                self._annotated_image = self._image_processor.annotate_image(image, self._boxes, self._classes, self._scores, threshold=threshold)
            self._sketcher = SketchGizeh()
            self._sketcher.setup(image.shape[1], image.shape[0])
            if max_objects:
                sorted_scores = sorted(self._scores.flatten())
                threshold = sorted_scores[-min([max_objects, self._scores.size])]
            self._image_labels = self._sketcher.draw_object_recognition_results(np.squeeze(self._boxes),
                                   np.squeeze(self._classes).astype(np.int32),
                                   np.squeeze(self._scores),
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
        cartoon_path = self._image_path.with_name('cartoon' + str(self.count) + '.png')
        labels_path = self._image_path.with_name('labels' + str(self.count) + '.txt')
        with open(str(labels_path), 'w') as f:
            f.writelines(self.image_labels)
        if debug:
            scores_path = self._image_path.with_name('scores' + str(self.count) + '.txt')
            with open(str(scores_path), 'w', newline='') as f:
                fcsv = writer(f)
                fcsv.writerow(map(str, self._scores.flatten()))
        if self._annotate:
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
        with open(str(path), 'wb') as f:
            writer = png.Writer(image.shape[1], image.shape[0], greyscale=False, bitdepth=8)
            writer.write(f, np.reshape(image, (-1, image.shape[1] * image.shape[2])))

    def close(self):
        self._image_processor.close()
        self.gpio.close()

    @property
    def image_labels(self):
        return self._image_labels
