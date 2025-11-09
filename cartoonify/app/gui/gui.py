import remi.gui as gui
from pathlib import Path
from remi import App, start
from app.workflow.multiprocessing import ProcessInterface
from app.debugging.tracing import trace
from app.debugging.logging import getLogger

# Import router and UI builders.
from app.gui.remi_multipath import RouterApp
from app.gui.maingui import build_main_ui, show_image_on_app
from app.gui.saygui import build_say_ui


class WebGui(RouterApp, ProcessInterface):
    """
    Main web GUI application with multi-path routing support.
    
    This App serves as a router, providing different UIs on different paths:
    - / : Main camera/capture interface
    - /say : Text-to-speech interface
    """
    
    # Routing configuration (set in hook_up before start()).
    _routes_config = {}
    _default_path = '/'
    
    def __init__(self, *args, **kwargs):
        """Initialize WebGui with routing configuration."""
        super().__init__(*args, **kwargs)
    
    @staticmethod
    def hook_up(event_service, exit_event, halt_event, i18n, cam_only, *args, **kwargs):
        """
        Static method called by ProcessManager to start the web server.
        
        Configures routing and starts the REMI server with WebGui as the App class.
        """
        logger = getLogger('WebGui')
        
        # Prepare userdata tuple that will be passed to App.__init__().
        userdata = (event_service, logger, exit_event, halt_event, i18n, cam_only)
        
        # Define routes: maps URL paths to UI builder functions.
        routes = {
            '/': lambda app, *ud: build_main_ui(app, *ud),
            '/say': lambda app, *ud: build_say_ui(app, *ud)
        }
        
        # Set class attributes BEFORE calling start().
        # REMI calls App(*userdata), so we can't pass routes via __init__ kwargs.
        WebGui._routes_config = routes
        WebGui._default_path = '/'
        
        # Start REMI server.
        start(
            WebGui,
            title='Cartoonify',
            userdata=userdata,
            address='0.0.0.0',
            port=8081,
            start_browser=False,
            multiple_instance=True,
            standalone=False
        )
    
    def idle(self):
        """Idle callback called periodically by REMI.
        
        Checks for exit events and performs cleanup.
        """
        try:
            if hasattr(self, '_exit_event') and self._exit_event.is_set():
                self._log.info('Exit event detected in WebGui - closing application.')
                self.close()
        except Exception as e:
            if hasattr(self, '_log'):
                self._log.warning(f'Could not check exit_event: {e}')
    
    def show_image(self, original, annotated, cartoon, image_labels):
        """Update displayed images (called from workflow).
        
        Args:
            original (str): Path to original image
            annotated (str): Path to annotated image
            cartoon (str): Path to cartoon image
            image_labels (list): List of detected object labels
        """
        show_image_on_app(self, original, annotated, cartoon, image_labels)