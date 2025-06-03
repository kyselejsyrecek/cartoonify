import os
import threading
import time
import queue
from picamera2 import Picamera2
import cv2
import uuid

class Camera():
    _instance = None
    _lock = threading.Lock()
    
    RESOLUTIONS = [(2028, 1520), (4056, 3040)]

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(Camera, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        with self._lock:
            if not self._initialized:
                tuningfile = Picamera2.load_tuning_file("imx477_scientific.json")
                self.picam2 = Picamera2(tuning=tuningfile)
                self._configure_settings()
                self.image_queue = queue.Queue()
                self.capturing = False
                self.exposure_list = [639, 1278, 2556, 5112, 10224] 
                self.capture_trigger = threading.Event()
                
                self.saving = True  # saver_thread should keep running            
                self.saver_threads = []  # list for saving threads
                for _ in range(4): # Play with this
                    saver_thread = threading.Thread(target=self.save_images)
                    saver_thread.daemon = True  # Set the thread to daemon so it automatically closes when the main program ends
                    saver_thread.start()
                    self.saver_threads.append(saver_thread)

                self.output_directory = os.path.join("app", "static", "output")
                if not os.path.exists(self.output_directory):
                    os.makedirs(self.output_directory)
                self.picam2.start()
                
                self._initialized = True

    def _configure_settings(self):
        self.minExpTime, self.maxExpTime = 100, 32000000
        self.picam2.still_configuration.buffer_count = 2
        self.picam2.still_configuration.transform.vflip = True
        self.picam2.still_configuration.main.size = self.RESOLUTIONS[1]
        self.picam2.still_configuration.main.format = ("RGB888")
        self.picam2.still_configuration.main.stride = None
        self.picam2.still_configuration.queue = True
        self.picam2.still_configuration.display = None
        self.picam2.still_configuration.encode = None
        self.picam2.still_configuration.lores = None
        self.picam2.still_configuration.raw = None
        self.picam2.still_configuration.controls.NoiseReductionMode = 0
        self.picam2.still_configuration.controls.FrameDurationLimits = (self.minExpTime, self.maxExpTime)
        self.picam2.configure("still")
        self.picam2.controls.AeEnable = False
        self.picam2.controls.AeMeteringMode = 0
        self.picam2.controls.Saturation = 1.0
        self.picam2.controls.Brightness = 0.0
        self.picam2.controls.Contrast = 1.0
        self.picam2.controls.AnalogueGain = 1.0
        self.picam2.controls.Sharpness = 1.0

    def start_exposure_cycling(self):   
        self.capturing = True
        self.capture_thread = threading.Thread(target=self._continuous_capture)
        self.capture_thread.start()
        
    def stop_exposure_cycling(self):   
        self.capturing = False
        self.saving = False
        for thread in self.saver_threads:
            thread.join()

    def trigger_capture(self):
        self.capture_trigger.set() 

    def empty_queue(self):
        try:
            while True:
                item = self.image_queue.get_nowait()
                # Optionally, do something with item
        except queue.Empty:
            pass
        
    def _continuous_capture(self):
        # Helper function to match exposure settings
        def match_exp(metadata, indexed_list):
            err_factor = 0.01
            err_exp_offset = 30
            exp = metadata["ExposureTime"]
            gain = metadata["AnalogueGain"]
            for want in indexed_list:
                want_exp, _ = want
                if abs(gain - 1.0) < err_factor and abs(exp - want_exp) < want_exp * err_factor + err_exp_offset:
                    return want
            return None

        exposure_index = 0  # To track the current exposure setting
        capture_id = None
        remaining_exposures = set()
        # Clear the queue
        self.empty_queue()
        while self.capturing:
            if not self.capture_trigger.is_set():
                target_exp = self.exposure_list[exposure_index]  # Get the target exposure
                _ = self.picam2.capture_metadata() # Get metadata otherwise the loop is too fast
                self.picam2.set_controls({"ExposureTime": target_exp, "AnalogueGain": 1.0})  # Set the camera controls

            if self.capture_trigger.is_set() and not remaining_exposures:
                start_time = time.time()  # Save the start time
                # Begin a new capture cycle
                capture_id = uuid.uuid4()  # Generate a unique ID for this capture cycle
                remaining_exposures = {(exp, i) for i, exp in enumerate(self.exposure_list)}  # Reset the exposures to be captured

            if remaining_exposures:
                # Capture and validate the image during a capture cycle
                request = self.picam2.capture_request()
                meta = request.get_metadata()
                image_data = request.make_buffer("main")
                request.release()
                print(f'Captured metadata: {meta["ExposureTime"]} and {meta["SensorTimestamp"]}')

                # Set the next exposure immediately
                exposure_index = (exposure_index + 1) % len(self.exposure_list)
                target_exp = self.exposure_list[exposure_index]
                self.picam2.set_controls({"ExposureTime": target_exp, "AnalogueGain": 1.0})

                matched_exp = match_exp(meta, remaining_exposures)
                if matched_exp:
                    _, i = matched_exp
                    image_info = {
                        "capture_id": capture_id,
                        "exposure": matched_exp[0],
                        "metadata": meta,
                        "image_data": image_data
                    }
                    self.image_queue.put(image_info)
                    remaining_exposures.remove(matched_exp)  # Remove the matched exposure from the remaining exposures
                    print(f'Used : {meta["ExposureTime"]} and {meta["DigitalGain"]}  ')
                    
            # If all exposures are captured, clear the capture trigger
            if self.capture_trigger.is_set() and not remaining_exposures:
                self.capture_trigger.clear()
                end_time = time.time()  # Save the end time
                elapsed_time = end_time - start_time  # Calculate elapsed time
                print(f"capture_multiple_exposures took {elapsed_time:.2f} seconds")

            # Cycle to the next exposure setting
            exposure_index = (exposure_index + 1) % len(self.exposure_list)
        

    def save_images(self):
        while self.saving or not self.image_queue.empty():
            if not self.saving:
                print(f"Still {self.image_queue.qsize()} images left to process")
            try:
                image_info = self.image_queue.get(timeout=1)
                capture_id = image_info["capture_id"]
                exposure = image_info["exposure"]
                image_data = image_info["image_data"]
                capture_dir = os.path.join(self.output_directory, str(capture_id))
                os.makedirs(capture_dir, exist_ok=True)
                filename = f"image_exposure_{exposure}.jpg"
                filepath = os.path.join(capture_dir, filename)
                cv2.imwrite(filepath, self.picam2.helpers.make_array(image_data, self.picam2.camera_configuration()["main"]))
                self.image_queue.task_done()
            except queue.Empty:
                if not self.saving:  # Check if saving should be stopped
                    break

if __name__ == "__main__":
    camera = Camera()
    camera.start_exposure_cycling()

    time.sleep(2)
    for _ in range(20):
        camera.trigger_capture()
        time.sleep(1.5) # Play with this
    
    camera.stop_exposure_cycling()