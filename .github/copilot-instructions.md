# Cartoonify AI Coding Agent Instructions

## Project Overview
Cartoonify is a Python-based polaroid camera that captures photos and converts them to cartoon sketches via object detection + drawing synthesis. Originally "Draw This" by Dan Macnish, this implementation supports both desktop and Raspberry Pi deployment with hardware integration (camera, GPIO, thermal printer, sensors).

## Architecture & Core Components

### Main Application Flow
- **Entry Point**: `cartoonify/run.py` - CLI with 30+ options for different deployment modes
- **Core Orchestrator**: `app/workflow/workflow.py` - Main `Workflow` class coordinates all subsystems
- **Event System**: `app/workflow/multiprocessing.py` - ProcessManager handles child processes via EventManager proxy

### Key Subsystems
1. **Object Detection**: TensorFlow v1 SSD MobileNet model via `app/image_processor/imageprocessor.py`
2. **Cartoon Generation**: `app/sketch/` converts detected objects to cartoon drawings using Google QuickDraw dataset
3. **Hardware I/O**: `app/io/` - GPIO, camera (Picamera2), IR receiver, clap detector, sound, accelerometer
4. **Web Interface**: `app/gui/gui.py` - REMI-based web GUI for remote control

### Build & Deployment Patterns
- **Desktop**: `ubuntu-build` + `requirements_desktop.txt` 
- **Raspberry Pi**: `raspi-build` + `requirements_raspi.txt` - includes GPIO, camera, system service setup
- **ICR Mode**: `icr-build` + `requirements_icr.txt` - for Advantech ICR compatible systems
- All builds use Python virtual environments with `python -m venv virtualenv`

## Development Workflows

### Running the Application
```bash
# Desktop mode (interactive)
python run.py

# Camera capture mode  
python run.py --camera

# Raspberry Pi headless with web interface
python run.py --raspi-headless --web-server --camera

# Batch processing
python run.py --batch-process --file-patterns "*.jpg *.png"
```

### Hardware GPIO Mapping (BCM)
- Power LED: 4, Recording LED: 27, Busy LED: 17
- Eye LEDs: 18 (big), 22 (small) 
- Buttons: 5 (capture), 6 (halt/shutdown)
- Proximity sensor: 13

### Multiprocessing Architecture
- Main process runs `Workflow` with EventManager server on 127.0.0.1:50000
- Child processes: WebGui, IrReceiver, ClapDetector, Accelerometer 
- All child processes implement `ProcessInterface.hook_up()` static method
- Event communication via `event_service` proxy with methods like `capture()`, `delayed_capture()`, `wink()`

## Codebase Conventions

### Async Task Pattern
Use `@async_task` decorator for GPIO event handlers:
```python
@async_task
def capture(self, e=None):
    if not self._lock.acquire(blocking=False):
        return  # Skip if operation in progress
    try:
        # Do work
    finally:
        self._lock.release()
```

### Logging & Error Handling
- Use `from app.debugging.logging import getLogger` - custom logger with ANSI color support
- All classes initialize with `self._logger = getLogger(self.__class__.__name__)`
- Stderr is redirected to logging system in `run.py` to suppress TensorFlow noise

### Configuration Management
- `app/utils/attributedict.py` provides dict-like config access via dot notation
- Default configs in `Workflow.__init__()` with CLI option overrides
- File paths use `pathlib.Path` throughout

### Camera & Image Processing
- Picamera2 for capture via `app/io/camera.py` 
- Image scaling/fitting logic in `ImageProcessor.load_image_into_numpy_array()`
- Object detection uses non-max suppression for box filtering
- Results saved as: `image{N}.jpg` (original), `cartoon{N}.png` (result), `labels{N}.txt` (detected objects)

## Critical Integration Points

### TensorFlow Model Loading
- Models downloaded to `downloads/detection_models/` on first run
- Uses TensorFlow v1 API with `tf.disable_v2_behavior()`
- Frozen graph loading pattern in `ImageProcessor.load_model()`

### Hardware Dependencies  
- GPIO operations wrapped in `available()` checks for graceful desktop fallback
- Camera setup requires system packages: `python3-picamera2`, `libcamera`
- Thermal printer: ZJ-58 via CUPS with custom PPD files in `zj-58/`

### Service Management (Raspberry Pi)
- System service: `/etc/init.d/cartoonify` runs application on boot
- Handles GPIO initialization, swap disable, Wi-Fi hotspot setup
- Exit code 42 triggers system shutdown via halt button

When editing this codebase, pay attention to the multiprocessing event system, hardware abstraction patterns, and the async task concurrency model. The application prioritizes robustness over performance due to embedded deployment constraints.

## Code Editing Guidelines

### File Content Loading
- Always load and review current file content before making any modifications.
- User may have selectively reverted changes or made additional modifications.
- Never assume file content is the same as in previous interactions.

### Content Preservation
- Do not modify output strings, log messages, or display text unless explicitly requested.
- Preserve existing functionality and behavior unless specifically asked to change it.

### Code Comments
- Write comments as complete sentences with proper punctuation and periods.
- Avoid response-style comments directed at the user (e.g., "This FIXES the issue you requested").
- Avoid all-caps emphasis in comments unless it's existing code style.
- Write descriptive, technical comments that explain functionality rather than implementation notes for specific requests.

### Import Organization
- Always add imports to the top/header of files, following the existing structured organization.
- Do not use local imports within functions unless absolutely necessary.
- Remove unused imports when refactoring code.
- Maintain consistent import ordering and grouping as established in the codebase.