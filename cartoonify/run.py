import logging
import datetime
from pathlib import Path
import sys
import os
import click
import gettext

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

def flatten(xss):
    return [x for xs in xss for x in xs]

@click.command()
@click.option('--camera', is_flag=True, help='Use this flag to enable captures from the Raspberry Pi camera.')
@click.option('--gui', is_flag=True, help='Enables GUI based on a web browser (requires a screen). Can only be combined with --raspi-headless.')
@click.option('--web-server', is_flag=True, help='Enables web interface, without starting a browser. Can only be combined with --raspi-headless.')
@click.option('--ip', default='0.0.0.0', help='IP address to listen on if switch --gui or --web-server is provided. Listening on all interfaces by default.')
@click.option('--port', type=int, default=8081, help='Port to listen on if switch --gui or --web-server is provided. Defaults to 8081.')
@click.option('--cert-file', type=str, default='/etc/ssl/certs/ssl-cert-snakeoil.pem', help='SSL certificate file.')
@click.option('--key-file', type=str, default='/etc/ssl/private/ssl-cert-snakeoil.key', help='SSL key file (private).')
@click.option('--icr-daemon', is_flag=True, help='Set Advantech ICR compatible mode.')
@click.option('--image-url', type=str, default="", help='Set image URL to download capture from in ICR mode (IP camera).')
@click.option('--offline-image', type=str, default="", help='Path to image to be copied to images/cartoon0.png when image from URL given by parameter --image-url cannot be retrieved.')
@click.option('--force-download', is_flag=True,help='Download data if missing, suppressing confirmation prompt.')
@click.option('--raspi-headless', is_flag=True, help='Run on Raspberry Pi with camera, trigger, printer and an IR receiver sensor (without GUI).')
@click.option('--no-ir-receiver', is_flag=True, help='Disable IR receiver sensor (only used when switch --raspi-headless is given).')
@click.option('--no-clap-detector', is_flag=True, help='Disable clap detector (only used when switch --raspi-headless is given).')
@click.option('--batch-process', is_flag=True, help='Process all images in current directory matching --file-pattern.')
@click.option('--file-patterns', type=str, default="*.jpg *.JPG *.jpeg *.JPEG", help='File patterns for batch processing. Defaults to *.jpg *.JPG *.jpeg *.JPEG. Should be quoted.')
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
@click.option('--fast-init', is_flag=True, help='Skip awakening animation to speed up initialization.')
@click.option('--rotate-180deg', is_flag=True, help='Rotate camera image by 180 degrees')
@click.option('--audio-backend', choices=['pulseaudio', 'alsa', 'native'], 
              help='Specify audio backend to use')
@click.option('--video-format', choices=['h264', 'mjpeg'], default='h264',
              help='Video recording format')
@click.option('--video-resolution', choices=['480p', '720p', '1080p', 'max'], default='1080p',
              help='Video recording resolution')
@click.option('--video-fps', choices=[30, 50, 60, 100, 120], type=int, default=30,
              help='Video recording frame rate')
@click.option('--volume', type=float, default=1.0, metavar='0.0-1.0',
              help='Audio volume (0.0 = mute, 1.0 = 100%%)')
@click.option('--no-accelerometer', is_flag=True, help='Disable accelerometer motion detection')
def run(**kwargs):
    # Redirect standard error output prematurely. Broken TensorFlow library and its
    # CUDA-related dependencies generate a bunch of error output which is irrelevant
    # for the user. This block and two-step import workaround can be discarded when
    # they are fixed.
    redirect_file = open(str(Path(__file__).parent / 'logs' / logging_filename), 'w')
    os.dup2(redirect_file.fileno(), sys.stderr.fileno())

    # Import the rest of the application including external libraries like TensorFlow
    # or CUDA-related libraries.
    from app.workflow import Workflow, exit_event
    from app.drawing_dataset import DrawingDataset
    from app.image_processor import ImageProcessor, tensorflow_model_name, model_path
    from app.sketch import SketchGizeh
    from os.path import join
    from app.gui import get_WebGui
    from remi import start
    import time

    root = Path(__file__).parent
    config = AttributeDict(kwargs)
    config.file_patterns = config.file_patterns.split()
    error = False

    # Localization
    _ = gettext.translation('cartoonify', str(root / 'app' / 'locales'), fallback=True)
    _.install()

    # init objects
    dataset = DrawingDataset(str(root / 'downloads/drawing_dataset'), str(root / 'app' / 'label_mapping.jsonl'),
                             config.force_download)
    imageprocessor = ImageProcessor(str(model_path),
                                    str(root / 'app' / 'object_detection' / 'data' / 'mscoco_label_map.pbtxt'),
                                    tensorflow_model_name, config.force_download)

    if config.raspi_headless:
        config.camera = True
    
    app = Workflow(dataset, imageprocessor, config)
    app.setup(setup_gpio=config.raspi_headless)

    if config.gui or config.web_server:
        if config.gui:
            print('starting gui...')
        else:
            print('starting HTTP server on address {}:{}...'.format(config.ip, config.port))
        web_gui = get_WebGui(app, i18n=_, cam_only=config.raspi_headless)
        start(web_gui, address=config.ip, port=config.port, start_browser=config.gui,
              certfile=config.cert_file, keyfile=config.key_file)
        #profiling.evaluation_point("web server started") # The start() function blocks forever.
        # We never get there during the life of the instance.
        #os.close(app._ir_receiver.dev.fd)
        print("done")
    else:
        while True:
            if config.raspi_headless:
                while True:
                    # Main loop of the parent process.
                    # From now on, app takes care of itself and waits for button press event from GPIO driver.
                    # This thread's only responsibility is not to die so that the program is not terminated.
                    # It now simply waits for the exit_event to be set.
                    try:
                        while not exit_event.is_set():
                            time.sleep(0.5) # Short pause to reduce CPU usage
                    except KeyboardInterrupt:
                        # This block might not be strictly necessary due to signal handler
                        # implemented within Workflow, but it's good practice for robustness.
                        print("Parent Process: KeyboardInterrupt caught, exiting.")
                        exit_event.set()
                    finally:
                        print("Parent Process: All processes and manager terminated.")

            elif config.camera:
                if click.confirm('would you like to capture an image? '):
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
                for file in flatten(sorted([list(path.glob(pattern)) for pattern in config.file_patterns])):
                    print('processing {}'.format(str(file)))
                    app.process(str(file))
                    annotated_path, cartoon_path = app.save_results(debug=config.debug_detection)
                    app.increment()
                    print(f'cartoon saved to {cartoon_path}')
                print('finished processing files, closing app.')
                break

            else:
                path = Path(input("enter the filepath of the image to process: "))
                if str(path) in ('', '.', 'exit'):
                    print("exiting on user request.")
                    break
                else:
                    app.process(str(path))
                    annotated_path, cartoon_path = app.save_results(debug=config.debug_detection)
                    app.increment()
                    print(f'cartoon saved to {cartoon_path}')
    app.close()

if __name__=='__main__':
    run()
    sys.exit()
