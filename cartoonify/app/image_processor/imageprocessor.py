import numpy as np
import os
import tarfile
import tensorflow.compat.v1 as tf

# TODO Tensorflow does not yet support limiting CPU resources in version 2.16.1.
#gpus = tf.config.list_physical_devices('GPU')
#if gpus:
#  print("Setting up GPU limits...")
#  # Restrict TensorFlow to only allocate 1GB of memory on the first GPU.
#  try:
#    #tf.config.threading.set_inter_op_parallelism_threads(2)
#    #tf.config.threading.set_intra_op_parallelism_threads(2)
#    #tf.config.experimental.set_memory_growth(gpus[0], True)
#    memory_limit_in_mb=1024
#    tf.config.set_logical_device_configuration(
#        gpus[0],
#        [tf.config.LogicalDeviceConfiguration(memory_limit=memory_limit_in_mb)])
#    logical_gpus = tf.config.list_logical_devices('GPU')
#    print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
#  except (RuntimeError, ValueError) as e:
#    # Virtual devices must be set before GPUs have been initialized
#    print(e)
#else:
#    print("No suitable GPU found. Computation will be done on CPU.")

from PIL import Image
from app.object_detection import label_map_util
from app.object_detection import visualization_utils as vis_util
from app.debugging.logging import getLogger
from pathlib import Path
import click


root = Path(__file__).parent
tensorflow_model_name = 'ssd_mobilenet_v1_coco_2017_11_17'
model_path = root / '..' / '..' / 'downloads' / 'detection_models' / tensorflow_model_name / 'frozen_inference_graph.pb'

# The SSD Mobilenet v1 COCO model utilizes TensorFlow v1 API. Set it as default.
tf.disable_v2_behavior()

class ImageProcessor(object):
    """performs object detection on an image
    """

    def __init__(self, path_to_model, path_to_labels, model_name, force_download=False):
        self._model_name = model_name
        # Path to frozen detection graph. This is the actual model that is used for the object detection.
        self._path_to_model = path_to_model
        # strings used to add correct label for each box.
        self._path_to_labels = path_to_labels
        self._download_url = 'http://download.tensorflow.org/models/object_detection/'
        self._force_download = force_download
        self._num_classes = 90
        self._detection_graph = None
        self._labels = dict()
        self._image = None
        self._boxes = None
        self._classes = None
        self._scores = None
        self._num = None
        self._log = None
        self._session = None
        self.image_tensor = None
        self.detection_boxes = None
        self.detection_scores = None
        self.detection_classes = None
        self.num_detections = None

    def setup(self):
        self._log = getLogger(self.__class__.__name__)
        if not Path(self._path_to_model).exists():
            if self._force_download or \
               click.confirm('no object detection model available, would you like to download the model? '
                             'download will take approx 100mb of space'):
                self.download_model(self._download_url, self._model_name + '.tar.gz')
        self.load_model(self._path_to_model)
        self._labels = self.load_labels(self._path_to_labels)
        # run a detection once, because first model run is always slow
        self.detect(np.ones((150, 150, 3), dtype=np.uint8), 1.0)

    def download_model(self, url, filename):
        """download a model file from the url and unzip it
        """
        import app.urllib
        self._log.info('downloading model: {}'.format(filename))
        for i in range(5):
            try:
                app.urllib.urlretrieve(url + filename, filename)
                break
            except:
                if i == 4: raise
        tar_file = tarfile.open(filename)
        for file in tar_file.getmembers():
            file_name = os.path.basename(file.name)
            if 'frozen_inference_graph.pb' in file_name:
                tar_file.extract(file, path=str(Path(self._path_to_model).parents[1]))
        os.remove(filename)

    def load_model(self, path):
        """load saved model from protobuf file
        """
        if not Path(path).exists():
            raise IOError('model file missing: {}'.format(str(path)))
        with tf.io.gfile.GFile(path, 'rb') as fid:
            graph_def = tf.GraphDef()
            graph_def.ParseFromString(fid.read())
        with tf.Graph().as_default() as graph:
            tf.import_graph_def(graph_def, name='')
        self._detection_graph = graph
        self._session = tf.Session(graph=self._detection_graph)
        # Definite input and output Tensors for detection_graph
        self.image_tensor = self._detection_graph.get_tensor_by_name('image_tensor:0')
        # Each box represents a part of the image where a particular object was detected.
        self.detection_boxes = self._detection_graph.get_tensor_by_name('detection_boxes:0')
        # Each score represent how level of confidence for each of the objects.
        # Score is shown on the result image, together with the class label.
        self.detection_scores = self._detection_graph.get_tensor_by_name('detection_scores:0')
        self.detection_classes = self._detection_graph.get_tensor_by_name('detection_classes:0')
        self.num_detections = self._detection_graph.get_tensor_by_name('num_detections:0')

    def load_labels(self, path):
        """load labels from .pb file, and map to a dict with integers, e.g. 1=aeroplane
        """
        label_map = label_map_util.load_labelmap(path)
        categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=self._num_classes,
                                                                    use_display_name=True)
        category_index = label_map_util.create_category_index(categories)
        return category_index

    def load_image_raw(self, path):
        """load raw image for later use with numpy
        """
        return Image.open(path)

    def load_image_into_numpy_array(self, raw_image, scale=1.0, fit_width=None, fit_height=None):
        """load raw image into NxNx3 numpy array
        """
        if fit_width:
            scale = float(fit_width) / raw_image.size[0]
        if fit_height:
            scale = min(scale, float(fit_height) / raw_image.size[1])
        (im_width, im_height) = [int(scale * dim) for dim in raw_image.size]
        raw_image = raw_image.resize([im_width, im_height])
        return np.array(raw_image.getdata()).reshape((im_height, im_width, 3)).astype(np.uint8)

    def detect(self, image, iou_threshold):
        """detect objects in the image
        """
        # Expand dimensions since the model expects images to have shape: [1, None, None, 3]
        image_np_expanded = np.expand_dims(image, axis=0)
        # Actual detection.
        # num is not used since it does not take score threshold into account
        (self._boxes, self._scores, self._classes, num) = self._session.run(
            [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections],
            feed_dict={self.image_tensor: image_np_expanded})
        selected_indices = tf.image.non_max_suppression(
            boxes           = self._boxes[0],
            scores          = self._scores[0],
            max_output_size = 100, # Arbitrary value, must be set.
            iou_threshold   = iou_threshold,
            name            = None)
        with tf.Session().as_default():
            self._boxes = tf.gather(self._boxes[0], selected_indices).eval()
            self._scores = tf.gather(self._scores[0], selected_indices).eval()
            self._classes = tf.gather(self._classes[0], selected_indices).eval()
        return self._boxes, self._scores, self._classes

    def annotate_image(self, image, boxes, classes, scores, threshold=0.5):
        """draws boxes around the detected objects and labels them

        :return: annotated image
        """
        annotated_image = image.copy()
        vis_util.visualize_boxes_and_labels_on_image_array(
            annotated_image,
            boxes,
            classes.astype(np.int32),
            scores,
            self._labels,
            use_normalized_coordinates=True,
            line_thickness=5,
            min_score_thresh=threshold)
        return annotated_image

    @property
    def labels(self):
        return self._labels

    def close(self):
        if self._session:
            self._session.close()
