import logging
import datetime
from pathlib import Path
import sys
import os
import click

from app.utils.attributedict import AttributeDict
from app.debugging import profiling

# BUG: Built-in input() function writes to stderr instead of stdout (Python 3.11).
# See https://discuss.python.org/t/builtin-function-input-writes-its-prompt-to-sys-stderr-and-not-to-sys-stdout/12955/2.
from builtins import input as __input
def input(prompt=""):
    print(prompt, end="")
    return __input()

# configure logging
logging_filename = datetime.datetime.now().strftime('%Y%m%d-%H%M.log')
logging_path = Path(__file__).parent / 'logs'
if not logging_path.exists():
    logging_path.mkdir()
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG, filename=str(Path(__file__).parent / 'logs' / logging_filename))

# Redirect standard error output prematurely. Broken TensorFlow library and its
# CUDA-related dependencies generate a bunch of error output which is irrelevant
# for the user. This block and two-step import workaround can be discarded when
# they are fixed.
redirect_file = open(str(Path(__file__).parent / 'logs' / logging_filename), 'w')
os.dup2(redirect_file.fileno(), sys.stderr.fileno())

def flatten(xss):
    return [x for xs in xss for x in xs]

@click.command()
@click.option('--camera', is_flag=True, help='Use this flag to enable captures from the Raspberry Pi camera.')
@click.option('--gui', is_flag=True, help='Enables GUI based on a web browser (requires a screen).')
@click.option('--web-server', is_flag=True, help='Enables web interface, without starting a browser.')
@click.option('--ip', default='0.0.0.0', help='IP address to listen on if switch --gui or --web-server is provided. Listening on all interfaces by default.')
@click.option('--port', type=int, default=8081, help='Port to listen on if switch --gui or --web-server is provided. Defaults to 8081.')
@click.option('--icr-daemon', is_flag=True, help='Set Advantech ICR compatible mode.')
@click.option('--image-url', type=str, default="", help='Set image URL to download capture from in ICR mode (IP camera).')
@click.option('--offline-image', type=str, default="", help='Path to image to be copied to images/cartoon0.png when image from URL given by parameter --image-url cannot be retrieved.')
@click.option('--force-download', is_flag=True,help='Download data if missing, suppressing confirmation prompt.')
@click.option('--raspi-headless', is_flag=True, help='Run on Raspberry Pi with camera, trigger and a printer (without GUI).')
@click.option('--batch-process', is_flag=True, help='Process all images in current directory matching --file-pattern.')
@click.option('--file-patterns', type=str, default="*.jpg *.JPG *.jpeg *.JPEG", help='File patterns for batch processing. Defaults to *.jpg *.JPG *.jpeg *.JPEG.')
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
@click.option('--max-image-number', type=int, default=10000, help='Maximal number of images to be stored. Numbering will be restarted from zero when the limit is reached. Defaults to 10,000.')
@click.option('--debug-detection', is_flag=True, help='Save a list of all detected object scores.')
def run(**kwargs):
    # Import the rest of the application including external libraries like TensorFlow
    # or CUDA-related libraries.
    from app.workflow import Workflow
    from app.drawing_dataset import DrawingDataset
    from app.image_processor import ImageProcessor, tensorflow_model_name, model_path
    from app.sketch import SketchGizeh
    from os.path import join
    from app.gui import get_WebGui
    from remi import start
    import importlib
    import time

    root = Path(__file__).parent
    config = AttributeDict(kwargs)
    config.file_patterns = config.file_patterns.split()

    # init objects
    dataset = DrawingDataset(str(root / 'downloads/drawing_dataset'), str(root / 'app/label_mapping.jsonl'),
                             config.force_download)
    imageprocessor = ImageProcessor(str(model_path),
                                    str(root / 'app' / 'object_detection' / 'data' / 'mscoco_label_map.pbtxt'),
                                    tensorflow_model_name, config.force_download)

    if config.camera or config.raspi_headless:
        try:
            picam = importlib.import_module('picamera2')
        except ImportError as e:
            print('picamera2 module missing, please install using:\n     pip install picamera2')
            logging.exception(e)
            sys.exit()
        cam = picam.Picamera2()
    else:
        cam = None
    app = Workflow(dataset, imageprocessor, cam, config)

    if config.gui or config.web_server:
        if config.gui:
            print('starting gui...')
        else:
            print('starting HTTP server on address {}:{}...'.format(config.ip, config.port))
        web_gui = get_WebGui(app)
        start(web_gui, address=config.ip, port=config.port, start_browser=config.gui)
        profiling.evaluation_point("web server started")
        print("done")
    else:
        app.setup(setup_gpio=config.raspi_headless)
        error = False
        while True:
            if config.raspi_headless:
                while True:
                    if app.get_capture_pin():
                        print('capture button pressed.')
                        app.run(print_cartoon=True)
                        time.sleep(0.02)

            elif config.camera:
                if click.confirm('would you like to capture an image? '):
                    path = root / 'images' / 'image.jpg'
                    if not path.parent.exists():
                        path.parent.mkdir()
                    app.capture(str(path))
                    app.process(str(path))
                    app.save_results(debug=config.debug_detection)
                else:
                    break

            elif config.icr_daemon: # TODO Convert to IP camera.
                import subprocess
                import time
                import traceback
                from app.urllib import urlretrieve as urlretrieve

                def get_cmd_output(command):
                    return subprocess.run(command, shell=True, text=True, capture_output=True).stdout.rstrip()
                    
                if get_cmd_output('io get out1') == '1':
                    logging.info('downloading image: {}'.format(config.image_url))
                    try:
                        urlretrieve(config.image_url, "camera0.jpg")
                        error = False
                        app.process("camera0.jpg")
                        app.save_results(debug=config.debug_detection)
                    except:
                        if not error:
                            error = True
                            from shutil import copy
                            copy(config.offline_image, "cartoon0.png")
                            logging.error('error downloading image: {}.\nSuppresing this message until first successful retrieval.'.format(traceback.format_exc()))
                time.sleep(1)

            elif config.batch_process:
                path = Path(input("enter the path to the directory to process: "))
                for file in flatten([list(path.glob(pattern)) for pattern in config.file_patterns]):
                    print('processing {}'.format(str(file)))
                    app.process(str(file))
                    app.save_results(debug=config.debug_detection)
                    app.increment()
                print('finished processing files, closing app.')
                break

            else:
                path = Path(input("enter the filepath of the image to process: "))
                if str(path) in ('', '.', 'exit'):
                    print("exiting on user request.")
                    break
                else:
                    app.process(str(path))
                    app.save_results(debug=config.debug_detection)
        app.close()

if __name__=='__main__':
    run()
    sys.exit()
