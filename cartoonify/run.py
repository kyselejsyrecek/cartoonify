import logging
import datetime
from pathlib import Path
import sys
import os
import atexit
import click
import gettext
import time

from app.utils.attributedict import AttributeDict
from app.debugging import profiling
from app.debugging.logging import setup_file_logging, setup_debug_logging, getLogger

# BUG: Built-in input() function writes to stderr instead of stdout (Python 3.11).
# See https://discuss.python.org/t/builtin-function-input-writes-its-prompt-to-sys-stderr-and-not-to-sys-stdout/12955/2.
from builtins import input as __input
def input(prompt=""):
    print(prompt, end="")
    return __input()

# configure logging
logs_dir = Path(__file__).parent / 'logs'

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
@click.option('--audio-backend', type=click.Choice(['pulseaudio', 'alsa', 'native']), 
              help='Specify audio backend to use')
@click.option('--video-format', type=click.Choice(['h264', 'mjpeg']), default='h264',
              help='Video recording format')
@click.option('--video-resolution', type=click.Choice(['480p', '720p', '1080p', 'max']), default='1080p',
              help='Video recording resolution')
@click.option('--video-fps', type=click.Choice([30, 50, 60, 100, 120]), default=30,
              help='Video recording frame rate')
@click.option('--video-raw-stream', is_flag=True, help='Save video as raw stream (.h264/.mjpeg) instead of standard container format (.mp4/.avi)')
@click.option('--volume', type=float, default=1.0, metavar='0.0-1.0',
              help='Audio volume (0.0 = mute, 1.0 = 100%%)')
@click.option('--alsa-numid', type=int, default=4,
              help='ALSA mixer control numid for volume adjustment')
@click.option('--no-accelerometer', is_flag=True, help='Disable accelerometer motion detection')
@click.option('--tts-language', type=str, default='cs', help='Text-to-speech language code (default: cs for Czech)')
@click.option('--no-log-colors', is_flag=True, help='Disable colored output in log messages')
@click.option('--no-sound', is_flag=True, default=False, help='Disable all sounds.')
@click.option('--cert-file', type=str, default=None, help='SSL certificate file for HTTPS server.')
@click.option('--key-file', type=str, default=None, help='SSL private key file for HTTPS server.')
@click.option('--debug', is_flag=True, help='Output all log messages to console instead of file. Error messages go to stderr, others to stdout.')
@click.option('--debug-cmdline', is_flag=True, help='Start interactive Python console for debugging instead of event waiting loop. Only compatible with --raspi-headless, --gui and --web-server.')
def run(**kwargs):
    # Configure logging based on command line options
    config = AttributeDict(kwargs)
    
    # Setup logging based on debug mode
    if config.debug:
        original_stdout, original_stderr, stderr_redirector = setup_debug_logging(use_colors=not config.no_log_colors)
    else:
        original_stdout, original_stderr, stderr_redirector = setup_file_logging(logs_dir, redirect_stderr=True, use_colors=not config.no_log_colors)
    
    # Standard error output had to be redirected first to the logging library.
    # Broken TensorFlow library and its CUDA-related dependencies generate a bunch
    # of error output which is irrelevant for the user.

    # Import the rest of the application including external libraries like TensorFlow
    # or CUDA-related libraries.
    from app.workflow import Workflow
    from app.drawing_dataset import DrawingDataset
    from app.image_processor import ImageProcessor, tensorflow_model_name, model_path
    from app.sketch import SketchGizeh
    from os.path import join

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
    
    app = Workflow(dataset, imageprocessor, config, i18n=_)
    
    try:
        app.setup(setup_gpio=config.raspi_headless)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            error_msg = ("Error: Address already in use by another process.\n"
                        "Another instance of the application may be running.\n"
                        "Please stop any existing instances and try again.")
            if original_stderr:
                original_stderr.write(error_msg + "\n")
                original_stderr.flush()
            else:
                print(error_msg, file=sys.stderr)
            sys.exit(1)
        else:
            # Re-raise other OSErrors
            raise

    # Create logger after workflow setup
    log = getLogger(__name__)

    # For headless mode or web GUI mode, use the same event waiting logic
    if config.raspi_headless or config.gui or config.web_server:
        if config.debug_cmdline:
            from app.debugging.console import DebugConsole
            from app.workflow import exit_event
            
            # Create and setup debug console
            console = DebugConsole()
            console.setup(
                stderr=original_stderr,
                stdout=original_stdout,
                locals_dict=locals()
            )
            
            # Start interactive console session
            console.start()
        else:
            wait_for_events(app, log)
    else:
        while True:
            if config.camera:
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
    
    # Cleanup: restore stderr before closing
    if stderr_redirector:
        stderr_redirector.restore()
    
    exit_event.set()
    app.close()

def wait_for_events(app, logger):
    """Wait for halt_event or exit_event and handle them appropriately"""
    from app.workflow import Workflow, exit_event, halt_event
    while True:
        try:
            if halt_event.is_set():
                logger.info('Halt event detected - shutting down the system.')
                app.close()
                sys.exit(42)
            elif exit_event.is_set():
                logger.info('Exiting on exit event.')
                app.close()
                sys.exit(0)
            time.sleep(0.5)  # Short pause to reduce CPU usage
        except KeyboardInterrupt:
            print("KeyboardInterrupt caught, exiting.")
            exit_event.set()
            app.close()
            sys.exit(0)

if __name__=='__main__':
    run()
    sys.exit()
