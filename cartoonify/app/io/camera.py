import logging
import importlib
import sys
import time
from pathlib import Path


class Camera(object):
    """Controls camera functionality using Picamera2"""

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._cam = None
        self._picam2 = None

    def setup(self, rotate_180deg=False):
        """Setup camera system
        
        :param rotate_180deg: Whether to rotate camera image by 180 degrees
        """
        self._logger.info('Setting up camera system...')
        
        # Import picamera2
        try:
            self._picam2 = importlib.import_module('picamera2')
        except ImportError as e:
            print('picamera2 module missing, please install using:\n     pip install picamera2')
            logging.exception(e)
            sys.exit()
        
        self._cam = self._picam2.Picamera2()
        
        if self._cam is not None:
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

            #picam2.Picamera2.load_tuning_file("imx477_scientific.json")
            #picam2 = picam2.Picamera2(tuning=tuningfile)
            capture_config = self._cam.create_still_configuration() # This param can be added: controls={"AeExposureMode":2}
            # video_capture_config = self._cam.create_video_configuration(main, lores=lores, display='lores',controls={"FrameRate": 30, "FrameDurationLimits": (33333, 33333)}, transform=Transform(hflip=1, vflip=1))
            
            # Enable raw capture for DNG files alongside JPEG
            capture_config = self._cam.create_still_configuration(
                main={"size": self._cam.sensor_resolution},
                raw={"size": self._cam.sensor_resolution}
            )
            
            # Apply 180-degree rotation if requested
            if rotate_180deg:
                from libcamera import Transform
                capture_config["transform"] = Transform(hflip=True, vflip=True)
                
            self._logger.info(f"AnalogueGain control limits: {self._cam.camera_controls['AnalogueGain']}")
            # TODO resolution = (640, 480)
            self._cam.configure(capture_config)
            
            # Import controls for camera setup
            from libcamera import controls
            self._cam.controls.AfMode = controls.AfModeEnum.Continuous
            #self._cam.controls.AnalogueGain = 1.0
            #self._cam.controls.ExposureTime = 0
            self._cam.controls.AeEnable = True
            self._cam.start()
            time.sleep(2) # FIXME Replace with lazy sleep instead? Is that even needed?

            #request = picam2.capture_request()
            #request.save("main", "test.jpg")
            #metadata = request.get_metadata()
            #print(f"ExposureTime: {metadata['ExposureTime']}  AnalogueGain: {metadata['AnalogueGain']} DigitalGain: {metadata['DigitalGain']}")
            #request.release()

    def capture_file(self, path):
        """Capture image to file (JPEG + DNG raw)
        
        :param path: Path to save the JPEG image (DNG will have same name with .dng extension)
        """
        if self._cam is not None:
            self._logger.info('capturing image')
            
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
                
                self._logger.info(f'Saved JPEG: {jpeg_path}')
                self._logger.info(f'Saved DNG: {dng_path}')
            finally:
                request.release()
        else:
            raise AttributeError("Camera not initialized")

    def close(self):
        """Close camera resources"""
        if self._cam is not None:
            self._cam.close()
            self._cam = None
        self._logger.info('Camera closed')