import sys
import time
import threading
from pathlib import Path

from app.debugging.logging import getLogger

from .base import BaseIODevice


class Camera(BaseIODevice):
    """Controls camera functionality using Picamera2.
    """

    def __init__(self, enabled: bool = True):
        BaseIODevice.__init__(self, enabled=enabled)
        
        self._log = getLogger(self.__class__.__name__)
        self._cam = None
        self._video_encoder = None
        self._video_output = None
        self._recording = False
        self._video_number = 0
        self._video_path = None
        self._video_thread = None
        self._video_config = None
        self._video_format = None
        self._video_resolution = None
        self._video_fps = None
        self._video_raw_stream = None
        self._available = False

    @property
    def is_recording(self):
        """Check if camera is currently recording.
        
        :return: True if recording is in progress, False otherwise
        """
        return self._recording

    def setup(self, rotate_180deg=False, video_format='h264', video_resolution='1080p', video_fps=30, video_raw_stream=False, enabled: bool | None = None):
        """Setup camera system
        
        :param rotate_180deg: Whether to rotate camera image by 180 degrees
        :param video_format: Video recording format ('h264' or 'mjpeg')
        :param video_resolution: Video resolution ('480p', '720p', '1080p', 'max')
        :param video_fps: Video frame rate (30, 50, 60, 100, 120)
        :param video_raw_stream: Whether to save as raw stream or container format
        :param enabled: Optional override of enabled flag (None keeps constructor state)
        """
        super().setup(enabled=enabled)
        if not self._enabled:
            self._log.info('Camera disabled.')
            return

        self._log.info('Setting up camera system...')
        
        # Store video settings
        self._video_format = video_format
        self._video_resolution = video_resolution
        self._video_fps = video_fps
        self._video_raw_stream = video_raw_stream
        
        # Define resolution mappings
        self._resolutions = {
            '480p': (640, 480),
            '720p': (1280, 720),
            '1080p': (1920, 1080),
            'max': (2304, 1296)
        }
        
        # Import picamera2 and encoders
        try:
            import picamera2
            from picamera2 import encoders
            from picamera2.outputs import FfmpegOutput
            self._encoders = encoders  # Store reference for use in other methods
            self._FfmpegOutput = FfmpegOutput  # Store reference for container output
        except ImportError:
            self._log.error('picamera2 module missing, please install using:\n     pip install picamera2')
            self._available = False
            return
        
        try:
            self._cam = picamera2.Picamera2()
        except:
            self._log.error('Camera not available.')
            return
        
        if self._cam is not None:
            # Get video resolution
            video_size = self._resolutions.get(video_resolution, (1920, 1080))
            
            # Create video configuration alongside still configuration
            self._video_config = self._cam.create_video_configuration(
                main={"size": video_size, "format": "RGB888"},
                controls={"FrameRate": video_fps}
            )

            #self.minExpTime, self.maxExpTime = 100, 32000000
            #self._cam.still_configuration.buffer_count = 2
            #self._cam.still_configuration.transform.vflip = True
            #self._cam.still_configuration.main.size = self.RESOLUTIONS[1]
            #self._cam.still_configuration.main.format = ("RGB888")
            #self._cam.still_configuration.main.stride = None
            #self._cam.still_configuration.queue = True
            #self._cam.still_configuration.display = None
            #self._cam.still_configuration.encode = None
            #self._cam.still_configuration.lores = None
            #self._cam.still_configuration.raw = None
            #self._cam.still_configuration.controls.NoiseReductionMode = 0
            #self._cam.still_configuration.controls.FrameDurationLimits = (self.minExpTime, self.maxExpTime)
            #self._cam.configure("still")
            #self._cam.controls.AeEnable = False
            #self._cam.controls.AeMeteringMode = 0
            #self._cam.controls.Saturation = 1.0
            #self._cam.controls.Brightness = 0.0
            #self._cam.controls.Contrast = 1.0
            #self._cam.controls.AnalogueGain = 1.0
            #self._cam.controls.Sharpness = 1.0

            #self._cam.camera_controls = {
            #    'ScalerCrops': ((0, 0, 0, 0), (65535, 65535, 65535, 65535), (0, 0, 0, 0)),
            #    'AeFlickerPeriod': (100, 1000000, None),
            #    'AfMode': (0, 2, 0),
            #    'AfSpeed': (0, 1, 0),
            #    'AfMetering': (0, 1, 0),
            #    'ExposureTime': (1, 66666, 20000),
            #    'AeFlickerMode': (0, 1, 0),
            #    'ExposureValue': (-8.0, 8.0, 0.0),
            #    'AeEnable': (False, True, None),
            #    'AeMeteringMode': (0, 3, 0),
            #    'HdrMode': (0, 4, 0),
            #    'Saturation': (0.0, 32.0, 1.0),
            #    'ColourTemperature': (100, 100000, None),
            #    'Contrast': (0.0, 32.0, 1.0),
            #    'AwbMode': (0, 7, 0),
            #    'SyncFrames': (1, 1000000, 100),
            #    'ColourGains': (0.0, 32.0, None),
            #    'AfWindows': ((0, 0, 0, 0), (65535, 65535, 65535, 65535), (0, 0, 0, 0)),
            #    'AwbEnable': (False, True, None),
            #    'AeExposureMode': (0, 3, 0),
            #    'SyncMode': (0, 2, 0),
            #    'Brightness': (-1.0, 1.0, 0.0),
            #    'Sharpness': (0.0, 16.0, 1.0),
            #    'NoiseReductionMode': (0, 4, 0),
            #    'StatsOutputEnable': (False, True, False),
            #    'AeConstraintMode': (0, 3, 0),
            #    'ScalerCrop': ((0, 0, 0, 0), (65535, 65535, 65535, 65535), (0, 0, 0, 0)),
            #    'FrameDurationLimits': (33333, 120000, 33333),
            #    'CnnEnableInputTensor': (False, True, False),
            #    'AfRange': (0, 2, 0),
            #    'AfTrigger': (0, 1, 0),
            #    'LensPosition': (0.0, 32.0, 1.0),
            #    'AnalogueGain': (1.0, 16.0, 1.0),
            #    'AfPause': (0, 2, 0)
            #}

            #picamera2.Picamera2.load_tuning_file("imx477_scientific.json")
            #self._cam = picamera2.Picamera2(tuning=tuningfile)
            
            # Enable raw capture for DNG files alongside JPEG
            capture_config = self._cam.create_still_configuration(
                main={"size": self._cam.sensor_resolution},
                raw={"size": self._cam.sensor_resolution}
            )
            # video_capture_config = self._cam.create_video_configuration(main, lores=lores, display='lores',controls={"FrameRate": 30, "FrameDurationLimits": (33333, 33333)}, transform=Transform(hflip=1, vflip=1))
            
            # Apply 180-degree rotation if requested
            if rotate_180deg:
                from libcamera import Transform
                capture_config["transform"] = Transform(hflip=True, vflip=True)
                self._video_config["transform"] = Transform(hflip=True, vflip=True)
                
            self._log.info(f"AnalogueGain control limits: {self._cam.camera_controls['AnalogueGain']}")
            # TODO resolution = (640, 480)
            self._cam.configure(capture_config)
            
            # Import controls for camera setup
            from libcamera import controls
            # Ensure continuous autofocus is active after start
            self._cam.controls.AfMode = controls.AfModeEnum.Continuous
            #self._cam.controls.AfTrigger = controls.AfTriggerEnum.Start
            #self._cam.controls.AnalogueGain = 1.0
            #self._cam.controls.ExposureTime = 0
            self._cam.controls.AeEnable = True
            
            # Start camera and give it time to initialize autofocus
            self._cam.start()
            time.sleep(2) # FIXME Replace with lazy sleep instead? Is that even needed?

            # Video recording setup.
            # Pre-create video encoder and output based on format and raw stream settings.
            if self._video_raw_stream:
                # Use raw stream encoders for direct file output.
                if self._video_format == 'h264':
                    self._video_encoder = self._encoders.H264Encoder()
                else:  # mjpeg
                    self._video_encoder = self._encoders.MJPEGEncoder()
            else:
                # Use encoder + FfmpegOutput for container formats.
                if self._video_format == 'h264':
                    # H.264 in MP4 container.
                    self._video_encoder = self._encoders.H264Encoder()
                else:  # mjpeg
                    # MJPEG in AVI container.
                    self._video_encoder = self._encoders.MJPEGEncoder()

            # Mark available only after successful init.
            self._available = True
            #request = self._cam.capture_request()
            #request.save("main", "test.jpg")
            #metadata = request.get_metadata()
            #print(f"ExposureTime: {metadata['ExposureTime']}  AnalogueGain: {metadata['AnalogueGain']} DigitalGain: {metadata['DigitalGain']}")
            #request.release()

    def capture_file(self, path):
        """Capture image to file (JPEG + DNG raw)
        
        :param path: Path to save the JPEG image (DNG will have same name with .dng extension)
        """
        if not self._enabled:
            raise AttributeError('Camera disabled')
        if self._available:
            self._log.info('capturing image')
            
            # Generate paths for both JPEG and DNG
            jpeg_path = Path(path)
            dng_path = jpeg_path.with_suffix('.dng')
            
            # Capture both JPEG and raw DNG
            request = self._cam.capture_request()
            try:
                # Save JPEG from main stream
                request.save("main", str(jpeg_path))
                
                # Save DNG from raw stream
                request.save_dng(str(dng_path))
                
                self._log.info(f'Saved JPEG: {jpeg_path}')
                self._log.info(f'Saved DNG: {dng_path}')
            finally:
                request.release()
        else:
            raise AttributeError('Camera not initialized or unavailable')

    def start_recording(self):
        """Start video recording in background thread"""
        if not self._enabled:
            self._log.warning('Camera disabled; ignoring start_recording.')
            return False
        if self._recording:
            self._log.warning('Recording already in progress')
            return False
            
        if self._cam is None or not self._available:
            self._log.error('Camera not initialized or unavailable')
            return False
            
        # Generate video filename based on format and raw stream setting.
        if self._video_raw_stream:
            # Raw stream: H264Encoder outputs .h264, MJPEGEncoder outputs .mjpeg.
            if self._video_format == 'h264':
                video_extension = 'h264'  # Raw H.264 stream.
            else:
                video_extension = 'mjpeg'  # MJPEG stream.
        else:
            # Container format: use FfmpegEncoder for standard containers.
            if self._video_format == 'h264':
                video_extension = 'mp4'  # H.264 in MP4 container.
            else:
                video_extension = 'avi'  # MJPEG in AVI container.
        self._video_path = Path(__file__).parent.parent.parent / 'images' / f'video{self._video_number}.{video_extension}'
        self._video_number += 1
        
        self._recording = True
        self._log.info(f'Starting video recording: {self._video_path}')
        
        # Start recording in separate thread to avoid blocking.
        self._video_thread = threading.Thread(target=self._record_video)
        self._video_thread.start()
        return True

    def stop_recording(self):
        """Stop video recording"""
        if not self._recording:
            self._log.warning('No recording in progress')
            return False
            
        self._recording = False
        self._log.info('Stopping video recording...')
        
        # Wait for recording thread to finish.
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=5)
            
        self._log.info(f'Video recording stopped: {self._video_path}')
        return True

    def _record_video(self):
        """Internal method to handle video recording"""
        try:
            # Switch to video configuration without stopping camera.
            self._cam.switch_mode(self._video_config)
            
            # Create output based on raw stream setting (encoder is already set up in setup()).
            if self._video_raw_stream:
                # Direct file output for raw streams.
                self._video_output = str(self._video_path)
            else:
                # FfmpegOutput for container formats.
                self._video_output = self._FfmpegOutput(str(self._video_path))

            # Start recording.
            self._cam.start_recording(self._video_encoder, self._video_output)
            
            # Keep recording until stopped.
            while self._recording:
                time.sleep(0.1)
                
        except Exception as e:
            self._log.exception(f'Video recording error: {e}')
        finally:
            # Stop recording.
            try:
                if self._video_encoder:
                    self._cam.stop_recording()
            except:
                pass

    def close(self):
        """Close camera resources"""
        # Stop recording if active.
        if self._recording:
            self.stop_recording()
            
        if self._cam is not None:
            self._cam.close()
            self._cam = None
        self._log.info('Camera closed')