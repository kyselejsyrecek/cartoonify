from __future__ import division
import click
from app.workflow import Workflow
from app.drawing_dataset import DrawingDataset
from app.image_processor import ImageProcessor, tensorflow_model_name, model_path
from app.sketch import SketchGizeh
from pathlib import Path
from os.path import join
import logging
import datetime
from app.gui import WebGui
from remi import start
import importlib
import sys
import time


root = Path(__file__).parent

# init objects
dataset = DrawingDataset(str(root / 'downloads/drawing_dataset'), str(root / 'app/label_mapping.jsonl'))
imageprocessor = ImageProcessor(str(model_path),
                                str(root / 'app' / 'object_detection' / 'data' / 'mscoco_label_map.pbtxt'),
                                tensorflow_model_name)

# configure logging
logging_filename = datetime.datetime.now().strftime('%Y%m%d-%H%M.log')
logging_path = Path(__file__).parent / 'logs'
if not logging_path.exists():
    logging_path.mkdir()
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG, filename=str(Path(__file__).parent / 'logs' / logging_filename))


@click.command()
@click.option('--camera', is_flag=True, help='Use this flag to enable captures from the Raspberry Pi camera.')
@click.option('--gui', is_flag=True, help='Enables GUI.')
@click.option('--raspi-headless', is_flag=True, help='Run on Raspberry Pi with camera and GPIO but without GUI.')
@click.option('--batch-process', is_flag=True, help='Process all *.jpg images in a directory.')
@click.option('--raspi-gpio', is_flag=True, help='Use GPIO to trigger capture & process.')
@click.option('--debug', is_flag=True, help='Save a list of all detected object scores.')
@click.option('--annotate', is_flag=True, help='Produce also annotated image.')
@click.option('--threshold', type=float, default=0.3, help='Threshold for object detection (0.0 to 1.0).')
@click.option('--max-overlapping', type=float, default=0.5, help='Threshold for the formula of area of two overlapping'
                                                                 'detection boxes intersection over area of their union (IOU).'
                                                                 'Detection box with higher fidelity is chosen over an overlapping'
                                                                 'detection box with lower fidelity if the computed IOU value'
                                                                 'of these boxes is higher than the given threshold (0.0 to 1.0).')
@click.option('--max-objects', type=int, default=None, help='Draw N objects with highest confidency at most.')
@click.option('--min-inference-dimension', type=int, default=512, help='Minimal inference image dimension in pixels.')
@click.option('--max-inference-dimension', type=int, default=1024, help='Maximal inference image dimension in pixels.')
@click.option('--fit-width', type=int, default=2048, help='Width of output rectangle in pixels which the resulting image is made to fit.')
@click.option('--fit-height', type=int, default=2048, help='Height of output rectangle in pixels which the resulting image is made to fit.')
def run(camera, gui, raspi_headless, batch_process, raspi_gpio, debug, annotate,
        threshold, max_overlapping, max_objects,
        min_inference_dimension, max_inference_dimension,
        fit_width, fit_height):
    if gui:
        print('starting gui...')
        start(WebGui, address='0.0.0.0', port=8081, start_browser=True)
    else:
        try:
            if camera or raspi_headless:
                picam = importlib.import_module('picamera')
                cam = picam.PiCamera()
                cam.rotation=90
            else:
                cam = None
            app = Workflow(dataset, imageprocessor, cam, annotate,
                           threshold, max_overlapping, max_objects,
                           min_inference_dimension, max_inference_dimension,
                           fit_width, fit_height)
            app.setup(setup_gpio=raspi_gpio)
        except ImportError as e:
            print('picamera module missing, please install using:\n     sudo apt-get update \n'
                  '     sudo apt-get install python-picamera')
            logging.exception(e)
            sys.exit()
        while True:
            if raspi_headless:
                while True:
                    if app.gpio.get_capture_pin():
                        print('capture button pressed.')
                        app.run(print_cartoon=True)
                        time.sleep(0.02)
            if camera:
                if click.confirm('would you like to capture an image?'):
                    path = root / 'images' / 'image.jpg'
                    if not path.parent.exists():
                        path.parent.mkdir()
                    app.capture(str(path))
                else:
                    app.close()
                    break
            if batch_process:
                path = Path(input("enter the path to the directory to process:"))
                for file in path.glob('*.jpg'):
                    print('processing {}'.format(str(file)))
                    app.process(str(file))
                    app.save_results(debug=debug)
                    app.count += 1
                print('finished processing files, closing app.')
                app.close()
                sys.exit()
            else:
                path = Path(input("enter the filepath of the image to process:"))
            if str(path) != '.' or 'exit':
                app.process(str(path))
                app.save_results(debug=debug)
            else:
                app.close()
                sys.exit()

if __name__=='__main__':
    run()
    sys.exit()
