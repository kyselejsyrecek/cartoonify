from app.debugging.logging import getLogger
import time
import threading
import importlib
from app.utils.asynctask import *
from app.workflow.multiprocessing import ProcessInterface


class Accelerometer(ProcessInterface):
    """Accelerometer/gyroscope motion detection using BMI160"""

    def __init__(self, log=None, exit_event=None, halt_event=None):
        self._log = log or getLogger(self.__class__.__name__)
        self._exit_event = exit_event
        self._halt_event = halt_event
        self._bmi160 = None
        self._sensor = None
        self._monitoring = False
        self._motion_callback = None
        self._last_motion_time = 0
        self._motion_cooldown = 5.0  # Default 5 seconds cooldown
        self._accel_threshold = 2.0  # Default g-force threshold for acceleration
        self._gyro_threshold = 100.0  # Default degrees/second threshold for gyroscope
        self._gyro_enabled = True  # Default gyroscope enabled
        self._async_executor = AsyncExecutor(max_workers=1)

    def setup(self, motion_callback=None, accel_threshold=2.0, gyro_threshold=100.0, 
              cooldown_time=5.0, gyro_enabled=True):
        """Setup accelerometer sensor
        
        :param motion_callback: Callback function to call on motion detection
        :param accel_threshold: Acceleration threshold in g-force for motion detection
        :param gyro_threshold: Gyroscope threshold in degrees/second for rotation detection
        :param cooldown_time: Time in seconds between motion detections
        :param gyro_enabled: Whether to enable gyroscope detection
        """
        self._log.info('Setting up accelerometer/gyroscope...')
        
        # Store configuration
        self._motion_callback = motion_callback
        self._accel_threshold = accel_threshold
        self._gyro_threshold = gyro_threshold
        self._motion_cooldown = cooldown_time
        self._gyro_enabled = gyro_enabled
        
        try:
            # Import BMI160 library
            self._bmi160 = importlib.import_module('BMI160_i2c')
            
            # Initialize sensor
            self._sensor = self._bmi160.BMI160()
            
            # Test sensor communication
            chip_id = self._sensor.getChipID()
            self._log.info(f'BMI160 chip ID: {chip_id}')
            
            if chip_id == 0xD1:  # BMI160 chip ID
                self._log.info('BMI160 sensor initialized successfully')
                self._log.info(f'Acceleration threshold: {self._accel_threshold}g')
                if self._gyro_enabled:
                    self._log.info(f'Gyroscope threshold: {self._gyro_threshold}°/s')
                else:
                    self._log.info('Gyroscope detection disabled')
                self._log.info(f'Motion cooldown: {self._motion_cooldown}s')
                self._start_monitoring()
            else:
                self._log.error(f'Invalid BMI160 chip ID: {chip_id}')
                self._sensor = None
                
        except ImportError as e:
            self._log.error('BMI160-i2c library not found. Install with: pip install BMI160-i2c')
            self._sensor = None
        except Exception as e:
            self._log.exception(f'Failed to initialize BMI160: {e}')
            self._sensor = None

    def _start_monitoring(self):
        """Start motion monitoring in background thread"""
        if self._sensor is None:
            return
            
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_motion, daemon=True)
        self._monitor_thread.start()
        self._log.info('Motion monitoring started')

    def _monitor_motion(self):
        """Monitor accelerometer and gyroscope for motion events"""
        while self._monitoring and self._sensor:
            try:
                motion_detected = False
                current_time = time.time()
                
                # Check if we're still in cooldown period
                if current_time - self._last_motion_time <= self._motion_cooldown:
                    time.sleep(0.1)
                    continue
                
                # Read accelerometer data
                accel_data = self._sensor.getAcceleration()
                if accel_data:
                    # Calculate total acceleration magnitude
                    x, y, z = accel_data
                    # Remove gravity component (assuming sensor is roughly level)
                    total_accel = abs(x) + abs(y) + abs(z - 1.0)
                    
                    # Check if acceleration exceeds threshold
                    if total_accel > self._accel_threshold:
                        self._log.info(f'Acceleration motion detected: {total_accel:.2f}g')
                        motion_detected = True
                
                # Read gyroscope data if enabled
                if self._gyro_enabled and not motion_detected:
                    gyro_data = self._sensor.getGyroscope()
                    if gyro_data:
                        # Calculate total rotation rate
                        x_rot, y_rot, z_rot = gyro_data
                        total_rotation = abs(x_rot) + abs(y_rot) + abs(z_rot)
                        
                        # Check if rotation exceeds threshold
                        if total_rotation > self._gyro_threshold:
                            self._log.info(f'Rotation motion detected: {total_rotation:.2f}°/s')
                            motion_detected = True
                
                # Trigger motion event if detected
                if motion_detected:
                    self._last_motion_time = current_time
                    
                    # Trigger motion callback asynchronously
                    if self._motion_callback:
                        self._trigger_motion_event()
                
                time.sleep(0.1)  # Check 10 times per second
                
            except Exception as e:
                self._log.exception(f'Error reading sensor: {e}')
                time.sleep(1)  # Wait longer on error

    @async_task
    def _trigger_motion_event(self):
        """Trigger motion event callback asynchronously"""
        try:
            if self._motion_callback:
                self._motion_callback()
        except Exception as e:
            self._log.exception(f'Error in motion callback: {e}')

    def close(self):
        """Stop monitoring and cleanup resources"""
        self._monitoring = False
        if hasattr(self, '_monitor_thread') and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)
        
        if self._sensor:
            self._sensor = None
            
        self._async_executor.close()
        self._log.info('Accelerometer closed')

    @staticmethod
    def hook_up(event_service, log, exit_event, halt_event, accel_threshold=2.0, gyro_threshold=100.0, cooldown_time=5.0, gyro_enabled=True):
        """Static method for multiprocessing integration.
        
        :param event_service: Event service proxy
        :param log: Logger instance for this process
        :param accel_threshold: Acceleration threshold in g-force
        :param gyro_threshold: Gyroscope threshold in degrees/second  
        :param cooldown_time: Time in seconds between motion detections
        :param gyro_enabled: Whether to enable gyroscope detection
        """
        accelerometer = Accelerometer(log, exit_event, halt_event)
        accelerometer.setup(
            motion_callback=event_service.dizzy,
            accel_threshold=accel_threshold,
            gyro_threshold=gyro_threshold, 
            cooldown_time=cooldown_time,
            gyro_enabled=gyro_enabled
        )
        return accelerometer