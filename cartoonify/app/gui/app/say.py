"""
Say GUI Application

This module contains the text-to-speech interface accessible at /say path.
"""

import remi.gui as gui
from remi import App, start

from app.workflow.multiprocessing import ProcessInterface


class SayWebGui(App, ProcessInterface):
    """
    Text-to-Speech GUI accessible at /say path.
    
    This App displays a simple form with:
    - Text input field.
    - Say button (speak the text).
    - Clear button (clear the input).
    - Back button (return to main page).
    """
    
    _event_service = None
    _log = None
    _i18n = None
    _exit_event = None
    _halt_event = None
    
    @staticmethod
    def hook_up(event_service, logger, exit_event, halt_event, i18n, 
                web_host='127.0.0.1', web_port=2000, start_browser=False,
                cert_file=None, key_file=None):
        try:
            logger.info(f'Starting SayWebGui on {web_host}:{web_port}')
            start(
                SayWebGui,
                debug=False,
                address=web_host,
                port=web_port,
                start_browser=start_browser,
                certfile=cert_file,
                keyfile=key_file,
                userdata=(event_service, logger, exit_event, halt_event, i18n)
            )
        except PermissionError:
            logger.error(f'Could not start SayWebGui - permission denied for {web_host}:{web_port}.')
        except Exception as e:
            logger.error(f'Error starting SayWebGui: {e}', exc_info=True)
    
    def idle(self):
        # idle function called every update cycle
        # Check for exit_event to gracefully shutdown SayWebGui
        try:
            if self._exit_event.is_set():
                self._log.info('Exit event detected in SayWebGui - closing application.')
                self.close()
        except Exception as e:
            self._log.warning(f'Could not check exit_event: {e}')
    
    def main(self, event_service, logger, exit_event, halt_event, i18n):
        self._event_service = event_service
        self._log = logger
        self._exit_event = exit_event
        self._halt_event = halt_event
        self._i18n = i18n
        
        self._log.debug(f'SayWebGui.main() called, path={getattr(self, "path", "unknown")}')
        
        return self.construct_ui()
    
    def construct_ui(self):
        """Construct the text-to-speech UI.
        
        Returns:
            Widget: The main container widget.
        """
        self._log.debug('Constructing Say UI')
        _ = self._i18n.gettext
        
        # Main container.
        main_container = gui.VBox()
        main_container.style.update({
            'top': '0px',
            'display': 'flex',
            'overflow': 'auto',
            'width': '100%',
            'flex-direction': 'column',
            'position': 'absolute',
            'justify-content': 'center',
            'margin': '0px',
            'align-items': 'center',
            'left': '0px',
            'height': '100%',
            'background-color': '#f0f0f0'
        })
        
        # Title.
        title = gui.Label(_('Text-to-Speech'))
        title.style.update({
            'font-size': '24px',
            'font-weight': 'bold',
            'margin': '20px',
            'text-align': 'center'
        })
        main_container.append(title)
        
        # Form container.
        form_container = gui.VBox()
        form_container.style.update({
            'width': '400px',
            'padding': '20px',
            'background-color': 'white',
            'border-radius': '10px',
            'box-shadow': '0 2px 10px rgba(0,0,0,0.1)'
        })
        
        # Text input label.
        text_label = gui.Label(_('Enter text to speak:'))
        text_label.style.update({
            'margin-bottom': '10px',
            'font-weight': 'bold'
        })
        form_container.append(text_label)
        
        # Text input field.
        self.text_input = gui.TextInput()
        self.text_input.style.update({
            'width': '100%',
            'height': '100px',
            'margin-bottom': '20px',
            'padding': '10px',
            'border': '1px solid #ccc',
            'border-radius': '5px',
            'font-size': '14px'
        })
        form_container.append(self.text_input)
        
        # Status label (for feedback).
        self.status_label = gui.Label('')
        self.status_label.style.update({
            'margin-bottom': '10px',
            'text-align': 'center',
            'color': '#666',
            'font-style': 'italic',
            'min-height': '20px'
        })
        form_container.append(self.status_label)
        
        # Button container.
        button_container = gui.HBox()
        button_container.style.update({
            'justify-content': 'space-between',
            'width': '100%'
        })
        
        # Say button.
        say_button = gui.Button(_('Say'))
        say_button.style.update({
            'background-color': '#4CAF50',
            'color': 'white',
            'padding': '10px 20px',
            'border': 'none',
            'border-radius': '5px',
            'font-size': '16px',
            'cursor': 'pointer',
            'flex': '1',
            'margin-right': '5px'
        })
        say_button.onclick.do(self.on_say_pressed)
        button_container.append(say_button)
        
        # Clear button.
        clear_button = gui.Button(_('Clear'))
        clear_button.style.update({
            'background-color': '#ff9800',
            'color': 'white',
            'padding': '10px 20px',
            'border': 'none',
            'border-radius': '5px',
            'font-size': '16px',
            'cursor': 'pointer',
            'flex': '1',
            'margin-left': '5px',
            'margin-right': '5px'
        })
        clear_button.onclick.do(self.on_clear_pressed)
        button_container.append(clear_button)
        
        # Back button.
        back_button = gui.Button(_('Back to Main'))
        back_button.style.update({
            'background-color': '#008CBA',
            'color': 'white',
            'padding': '10px 20px',
            'border': 'none',
            'border-radius': '5px',
            'font-size': '16px',
            'cursor': 'pointer',
            'flex': '1',
            'margin-left': '5px'
        })
        back_button.onclick.do(self.on_back_pressed)
        button_container.append(back_button)
        
        form_container.append(button_container)
        main_container.append(form_container)
        
        return main_container
    
    def on_say_pressed(self, *_):
        """Handle Say button press."""
        text = self.text_input.get_value().strip()
        if text:
            self._log.info(f'Saying: {text}')
            self._event_service.say(text)
            # Update status.
            _ = self._i18n.gettext
            self.status_label.set_text(_('Speaking...'))
        else:
            _ = self._i18n.gettext
            self.status_label.set_text(_('Please enter some text'))
    
    def on_clear_pressed(self, *_):
        """Handle Clear button press."""
        self.text_input.set_value('')
        self.status_label.set_text('')
    
    def on_back_pressed(self, *_):
        """Handle Back to Main button press."""
        # Redirect to main page using JavaScript.
        try:
            self.execute_javascript("window.location.href = '/';")
        except Exception as e:
            self._log.warning(f'Could not redirect to main page: {e}')