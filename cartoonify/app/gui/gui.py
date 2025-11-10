import remi.gui as gui
import PIL.Image
import io
import time
import importlib
import os
import sys

from pathlib import Path
from app.workflow.multiprocessing import ProcessInterface
from app.debugging.tracing import trace
from app.debugging.logging import getLogger

# Import our router extension and target App classes.
from app.gui.router import start as router_start
from app.gui.gui_main import MainGui
from app.gui.gui_say import SayGui


class WebGui(ProcessInterface):
    """
    WebGui integration for multiprocessing.
    
    This class serves as the ProcessInterface implementation that integrates
    with the router system. It doesn't inherit from App - instead it uses
    MainGui and SayGui as separate App classes for different URL paths.
    
    The router system handles:
    - Routing / to MainGui.
    - Routing /say to SayGui.
    - Passing userdata to both Apps.
    - Managing App lifecycle.
    """
    
    @staticmethod
    def hook_up(event_service, logger, exit_event, halt_event, i18n, cam_only, 
                web_host='0.0.0.0', web_port=8081, start_browser=False, 
                cert_file=None, key_file=None):
        """Static method for multiprocessing integration.
        
        This is called by ProcessManager to start the web server.
        
        Args:
            event_service: Event service proxy for inter-process communication.
            logger: Logger instance.
            exit_event: Event for application exit.
            halt_event: Event for system halt.
            i18n: Internationalization helper.
            cam_only: Boolean flag for camera-only mode.
            web_host: Host address for web server (default: '0.0.0.0').
            web_port: Port for web server (default: 8081).
            start_browser: Whether to start browser automatically (default: False).
            cert_file: SSL certificate file path (optional).
            key_file: SSL key file path (optional).
        """
        try:
            # Define routes: URL path -> App class mapping.
            routes = {
                '/': MainGui,
                '/say': SayGui
            }
            
            # Prepare userdata tuple that will be passed to each App's main().
            userdata = (event_service, logger, exit_event, halt_event, i18n, cam_only)
            
            logger.info(f'Starting WebGui with routes: {list(routes.keys())}')
            logger.debug(f'Userdata: event_service={event_service}, logger={logger}, '
                        f'exit_event={exit_event}, halt_event={halt_event}, '
                        f'i18n={i18n}, cam_only={cam_only}')
            
            # Start REMI server with routing.
            # This call blocks until server stops.
            with trace():
                router_start(
                    routes,
                    debug=False,
                    address=web_host,
                    port=web_port,
                    start_browser=start_browser,
                    certfile=cert_file,
                    keyfile=key_file,
                    userdata=userdata,
                    default_path='/'
                )
        except PermissionError:
            logger.error(f'Could not start HTTP server - permission denied for {web_host}:{web_port}.')
        except Exception as e:
            logger.exception(f'Error starting WebGui: {e}')


# Remove old WebGui App class code below this point.
# The PILImageViewerWidget is now in gui_main.py.
# All UI construction is in MainGui (gui_main.py) and SayGui (gui_say.py).