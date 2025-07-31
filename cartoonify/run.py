import logging
import datetime
from pathlib import Path
import sys
import os
import click
import gettext
import time

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

# Custom formatter to extract only class name and align messages
class CustomFormatter(logging.Formatter):
    # ANSI color codes for terminal output
    COLORS = {
        'DEBUG': '\033[90m',      # Gray (dark white) - entire line
        'INFO': '\033[37m',       # White
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[41;93m', # Yellow text on red background
        'RESET': '\033[0m',       # Reset to default
        'BOLD': '\033[1m',        # Bold text
        'WHITE_BOLD': '\033[1;97m' # Bold bright white
    }
    
    def __init__(self, use_colors=None):
        super().__init__()
        # Auto-detect if we should use colors
        if use_colors is None:
            self.use_colors = self._should_use_colors()
        else:
            self.use_colors = use_colors
    
    def _should_use_colors(self):
        """Check if terminal supports colors"""
        import os
        # Check if output is a terminal and supports colors
        return (
            hasattr(sys.stderr, 'isatty') and sys.stderr.isatty() and
            os.environ.get('TERM', '').lower() not in ('', 'dumb') and
            os.environ.get('NO_COLOR', '').lower() not in ('1', 'true', 'yes')
        )
    
    def format(self, record):
        # Extract just the class name from logger name (e.g., picamera2.picamera2 -> picamera2)
        logger_name = record.name
        if '.' in logger_name:
            # Take the last part after the last dot
            class_name = logger_name.split('.')[-1]
        else:
            class_name = logger_name
        
        # Create aligned format with time in brackets, severity, and right-aligned class name
        formatted_time = self.formatTime(record, '%H:%M:%S.%f')[:-3]  # Remove last 3 digits for milliseconds
        # Right-align severity to 7 characters and class name to 15 characters
        aligned_severity = f"{record.levelname:>7}"
        aligned_class_name = f"{class_name:>15}"
        
        # Apply colors if terminal supports them
        if self.use_colors:
            if record.levelname == 'DEBUG':
                # Entire DEBUG line is gray with bold severity
                bold_debug_severity = f"{self.COLORS['BOLD']}{self.COLORS['DEBUG']}{aligned_severity}{self.COLORS['RESET']}"
                formatted_message = f"{self.COLORS['DEBUG']}[{formatted_time}] {bold_debug_severity} {aligned_class_name}: {record.getMessage()}{self.COLORS['RESET']}"
            elif record.levelname == 'CRITICAL':
                # Entire CRITICAL line with background color
                formatted_message = f"{self.COLORS['CRITICAL']}[{formatted_time}] {aligned_severity} {aligned_class_name}: {record.getMessage()}{self.COLORS['RESET']}"
            else:
                # Other levels: bold severity + bold white class name
                severity_color = self.COLORS.get(record.levelname, '')
                bold_severity = f"{self.COLORS['BOLD']}{severity_color}{aligned_severity}{self.COLORS['RESET']}"
                bold_class_name = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                formatted_message = f"[{formatted_time}] {bold_severity} {bold_class_name}: {record.getMessage()}"
        else:
            formatted_message = f"[{formatted_time}] {aligned_severity} {aligned_class_name}: {record.getMessage()}"
        
        # Handle exceptions
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            if self.use_colors:
                if record.levelname == 'DEBUG':
                    # Gray exceptions for DEBUG
                    formatted_message += f"\n{self.COLORS['DEBUG']}{exception_text}{self.COLORS['RESET']}"
                elif record.levelname == 'CRITICAL':
                    # Critical background for CRITICAL exceptions
                    formatted_message += f"\n{self.COLORS['CRITICAL']}{exception_text}{self.COLORS['RESET']}"
                else:
                    # Format exceptions with ERROR severity and normal white text
                    error_severity = f"{self.COLORS['BOLD']}{self.COLORS['ERROR']}   ERROR{self.COLORS['RESET']}"
                    bold_class_name = f"{self.COLORS['WHITE_BOLD']}{aligned_class_name}{self.COLORS['RESET']}"
                    # Split exception text into lines and format each with ERROR prefix
                    exception_lines = exception_text.split('\n')
                    formatted_exception = []
                    for i, line in enumerate(exception_lines):
                        if i == 0:
                            # First line gets full ERROR formatting
                            formatted_exception.append(f"[{formatted_time}] {error_severity} {bold_class_name}: {line}")
                        else:
                            # Subsequent lines are just indented with spaces to align with message
                            spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)  # time + severity + space + class + ": "
                            formatted_exception.append(f"{spaces}{line}")
                    formatted_message += '\n' + '\n'.join(formatted_exception)
            else:
                # Plain text exceptions with ERROR prefix
                exception_lines = exception_text.split('\n')
                formatted_exception = []
                for i, line in enumerate(exception_lines):
                    if i == 0:
                        formatted_exception.append(f"[{formatted_time}]    ERROR {aligned_class_name}: {line}")
                    else:
                        spaces = ' ' * (len(f"[{formatted_time}] ") + 7 + 1 + 15 + 2)
                        formatted_exception.append(f"{spaces}{line}")
                formatted_message += '\n' + '\n'.join(formatted_exception)
        
        return formatted_message

# Configure logging with custom formatter
log_file = str(Path(__file__).parent / 'logs' / logging_filename)
handler = logging.FileHandler(log_file)
formatter = CustomFormatter(use_colors=False)  # File handler never uses colors
handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[handler]
)

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
@click.option('--video-fps', type=click.Choice(['30', '50', '60', '100', '120']), default='30',
              help='Video recording frame rate')
@click.option('--volume', type=float, default=1.0, metavar='0.0-1.0',
              help='Audio volume (0.0 = mute, 1.0 = 100%%)')
@click.option('--alsa-numid', type=int, default=4,
              help='ALSA mixer control numid for volume adjustment')
@click.option('--no-accelerometer', is_flag=True, help='Disable accelerometer motion detection')
@click.option('--tts-language', type=str, default='cs', help='Text-to-speech language code (default: cs for Czech)')
@click.option('--no-log-colors', is_flag=True, help='Disable colored output in log messages')
@click.option('--no-sound', is_flag=True, help='Disable all sound output and text-to-speech')
def run(**kwargs):
    # Configure logging based on command line options
    config = AttributeDict(kwargs)
    
    # Add console handler with colors if needed
    if not config.no_log_colors:
        console_handler = logging.StreamHandler(sys.stderr)
        console_formatter = CustomFormatter(use_colors=True)
        console_handler.setFormatter(console_formatter)
        logging.getLogger().addHandler(console_handler)
    
    # Redirect standard error output prematurely. Broken TensorFlow library and its
    # CUDA-related dependencies generate a bunch of error output which is irrelevant
    # for the user. This block and two-step import workaround can be discarded when
    # they are fixed.
    redirect_file = open(str(Path(__file__).parent / 'logs' / logging_filename), 'w')
    os.dup2(redirect_file.fileno(), sys.stderr.fileno())

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
    app.setup(setup_gpio=config.raspi_headless)

    # Create logger after workflow setup
    logger = logging.getLogger(__name__)

    # For headless mode or web GUI mode, use the same event waiting logic
    if config.raspi_headless or config.gui or config.web_server:
        wait_for_events(app, logger)
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
