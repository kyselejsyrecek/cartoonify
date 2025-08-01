import remi.gui as gui
import PIL.Image
import io
import time
import importlib
from app.debugging.logging import getLogger
import sys

from pathlib import Path
from remi import App, start
from app.workflow.multiprocessing import ProcessInterface


class PILImageViewerWidget(gui.Image):
    def __init__(self, **kwargs):
        super(PILImageViewerWidget, self).__init__(**kwargs)
        self._buf = None
        initial_image = str(Path(__file__).parent / '..' / '..' / 'images' / 'default.png')
        self.load(initial_image)

    def load(self, file_path_name):
        pil_image = PIL.Image.open(file_path_name)
        self._buf = io.BytesIO()
        pil_image.save(self._buf, format='png')
        self.refresh()

    def refresh(self):
        i = int(time.time() * 1e6)
        self.attributes['src'] = "/%s/get_image_data?update_index=%d" % (id(self), i)

    def get_image_data(self, update_index):
        if self._buf is None:
            return None
        self._buf.seek(0)
        headers = {'Content-type': 'image/png'}
        return [self._buf.read(), headers]


class WebGui(App, ProcessInterface):
    """
    gui for the app
    """

    def __init__(self, *args):
        super().__init__(*args)
        self._event_service = None
        self._i18n = None
        self._full_capabilities = True
        self._logger = getLogger("WebGui")

    @staticmethod
    def hook_up(event_service, logger, i18n, cam_only, web_host='0.0.0.0', web_port=8081):
        """Static method for multiprocessing integration."""
        # TODO
        # Register the /say route
        #from remi.server import remi_server
        
        #def say_page_handler():
        #    app = WebGui()
        #    app._event_service = event_service
        #    app._i18n = i18n
        #    app._full_capabilities = not cam_only
        #    app._logger = logger
        #    return app.construct_say_ui()
        
        # Register the route before starting
        #remi_server.add_resource('/say', say_page_handler)
        
        start(WebGui, 
              debug=False, 
              address=web_host, 
              port=web_port, 
              userdata=(event_service, logger, i18n, cam_only))

    def idle(self):
        # idle function called every update cycle
        # Check for exit_event to gracefully shutdown WebGui
        try:
            if hasattr(self._event_service, 'exit_event') and self._event_service.exit_event.is_set():
                self._logger.info('Exit event detected in WebGui - closing application.')
                self.close()
        except Exception as e:
            self._logger.warning(f'Could not check exit_event: {e}')
        pass

    def main(self, event_service, logger, i18n, cam_only):
        self._event_service = event_service
        self._logger = logger
        self._i18n = i18n
        self._full_capabilities = not cam_only
        
        self.display_original = False
        #self.display_tagged = False # TODO Not yet implemented.
        ui = self.construct_ui()
        return ui

    def construct_ui(self):
        _ = self._i18n.gettext
        # layout
        self.main_container = gui.VBox()
        self.main_container.style['top'] = "0px"
        self.main_container.style['display'] = "flex"
        self.main_container.style['overflow'] = "auto"
        self.main_container.style['width'] = "100%"
        self.main_container.style['flex-direction'] = "column"
        self.main_container.style['position'] = "absolute"
        self.main_container.style['justify-content'] = "space-around"
        self.main_container.style['margin'] = "0px"
        self.main_container.style['align-items'] = "center"
        self.main_container.style['left'] = "0px"
        self.main_container.style['height'] = "100%"
        hbox_snap = gui.HBox()
        hbox_snap.style['left'] = "0px"
        hbox_snap.style['order'] = "4348867584"
        hbox_snap.style['display'] = "flex"
        hbox_snap.style['overflow'] = "auto"
        hbox_snap.style['width'] = "70%"
        hbox_snap.style['flex-direction'] = "row"
        hbox_snap.style['position'] = "static"
        hbox_snap.style['justify-content'] = "space-around"
        hbox_snap.style['-webkit-order'] = "4348867584"
        hbox_snap.style['margin'] = "0px"
        hbox_snap.style['align-items'] = "center"
        hbox_snap.style['top'] = "125px"
        hbox_snap.style['height'] = "150px"
        button_snap = gui.Button(_('Snap'))
        button_snap.style['margin'] = "0px"
        button_snap.style['overflow'] = "auto"
        button_snap.style['width'] = "200px"
        button_snap.style['height'] = "30px"
        hbox_snap.append(button_snap, 'button_snap')
        if self._full_capabilities:
            button_open = gui.Button(_('Open image'))
            button_open.style['margin'] = "0px"
            button_open.style['overflow'] = "auto"
            button_open.style['width'] = "200px"
            button_open.style['height'] = "30px"
            hbox_snap.append(button_open, 'button_open')
        vbox_settings = gui.VBox()
        vbox_settings.style['order'] = "4349486136"
        vbox_settings.style['display'] = "flex"
        #vbox_settings.style['overflow'] = "auto"
        vbox_settings.style['width'] = "250px"
        vbox_settings.style['flex-direction'] = "column"
        vbox_settings.style['position'] = "static"
        vbox_settings.style['justify-content'] = "space-around"
        vbox_settings.style['-webkit-order'] = "4349486136"
        vbox_settings.style['margin'] = "0px"
        vbox_settings.style['align-items'] = "center"
        vbox_settings.style['top'] = "149.734375px"
        vbox_settings.style['height'] = "80px"
        checkbox_display_original = gui.CheckBoxLabel(_(' Display original image'), False, '')
        checkbox_display_original.style['margin'] = "0px"
        checkbox_display_original.style['margin-left'] = "35px"
        checkbox_display_original.style['align-items'] = "center"
        checkbox_display_original.style['width'] = "200px"
        checkbox_display_original.style['top'] = "135.734375px"
        checkbox_display_original.style['position'] = "static"
        checkbox_display_original.style['height'] = "30px"
        vbox_settings.append(checkbox_display_original, 'checkbox_display_original')
        #checkbox_display_tagged = gui.CheckBoxLabel(_(' Display tagged image'), False, '')
        #checkbox_display_tagged.style['margin'] = "0px"
        #checkbox_display_tagged.style['width'] = "200px"
        #checkbox_display_tagged.style['top'] = "135px"
        #checkbox_display_tagged.style['position'] = "static"
        #checkbox_display_tagged.style['height'] = "30px"
        #vbox_settings.append(checkbox_display_tagged, 'checkbox_display_tagged')
        hbox_snap.append(vbox_settings, 'vbox_settings')
        if self._full_capabilities:
            button_close = gui.Button(_('Terminate'))
            button_close.style['background-color'] = 'red'
            button_close.style['width'] = "200px"
            button_close.style['height'] = '30px'
            hbox_snap.append(button_close, 'button_close')
        self.main_container.append(hbox_snap, 'hbox_snap')
        height = 300
        self.image_original = PILImageViewerWidget(height=height)
        self.image_original.style['display'] = "block" if self.display_original else "none"
        self.main_container.append(self.image_original, 'image_original')
        self.image_result = PILImageViewerWidget(height=height)
        self.main_container.append(self.image_result, 'image_result')
        if self._full_capabilities:
            self.image_label = gui.Label('', width=400, height=30, margin='10px')
            self.image_label.style['text-align'] = "center"
            self.main_container.append(self.image_label, 'image_label')

        # event handlers
        button_snap.onclick.do(self.on_snap_pressed)
        if self._full_capabilities:
            button_open.onclick.do(self.on_open_pressed)
            button_close.onclick.do(self.on_close_pressed)
        checkbox_display_original.onchange.do(self.on_display_original_change)
        #checkbox_display_tagged.onchange.do(self.on_display_tagged_change)

        return self.main_container

    def construct_say_ui(self):
        """Construct the /say page UI"""
        _ = self._i18n.gettext
        
        # Main container
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
        
        # Title
        title = gui.Label(_('Text-to-Speech'))
        title.style.update({
            'font-size': '24px',
            'font-weight': 'bold',
            'margin': '20px',
            'text-align': 'center'
        })
        main_container.append(title)
        
        # Form container
        form_container = gui.VBox()
        form_container.style.update({
            'width': '400px',
            'padding': '20px',
            'background-color': 'white',
            'border-radius': '10px',
            'box-shadow': '0 2px 10px rgba(0,0,0,0.1)'
        })
        
        # Text input label
        text_label = gui.Label(_('Enter text to speak:'))
        text_label.style.update({
            'margin-bottom': '10px',
            'font-weight': 'bold'
        })
        form_container.append(text_label)
        
        # Text input field
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
        
        # Button container
        button_container = gui.HBox()
        button_container.style.update({
            'justify-content': 'space-between',
            'width': '100%'
        })
        
        # Say button
        say_button = gui.Button(_('Say'))
        say_button.style.update({
            'background-color': '#4CAF50',
            'color': 'white',
            'padding': '10px 20px',
            'border': 'none',
            'border-radius': '5px',
            'font-size': '16px',
            'cursor': 'pointer'
        })
        say_button.onclick.do(self.on_say_pressed)
        button_container.append(say_button)
        
        # Back button
        back_button = gui.Button(_('Back to Main'))
        back_button.style.update({
            'background-color': '#008CBA',
            'color': 'white',
            'padding': '10px 20px',
            'border': 'none',
            'border-radius': '5px',
            'font-size': '16px',
            'cursor': 'pointer'
        })
        back_button.onclick.do(self.on_back_pressed)
        button_container.append(back_button)
        
        form_container.append(button_container)
        main_container.append(form_container)
        
        return main_container

    def on_display_original_change(self, widget, value):
        self.display_original = value
        self.image_original.style['display'] = "block" if self.display_original else "none"

    #def on_display_tagged_change(self, widget, value):
    #    self.display_tagged = value

    def on_close_pressed(self, *_):
        self._event_service.close()
        self.close()  #closes the application
        # sys.exit()

    def on_snap_pressed(self, *_):
        # FIXME Seems to be sometimes still called with a delay when another print operation is in progress.
        self._event_service.capture() 

    def on_open_pressed(self, *_):
        self.fileselectionDialog = gui.FileSelectionDialog(_('File Selection Dialog'), _('Select an image file'), False, '.')
        self.fileselectionDialog.onchange.do(self.process_image)
        self.fileselectionDialog.set_on_cancel_dialog_listener(
            self.on_dialog_cancel)
        # here is shown the dialog as root widget.
        self.fileselectionDialog.show(self)

    def process_image(self, widget, file_list):
        if len(file_list) != 1:
            return
        original = file_list[0]
        self._event_service.process(original)
        annotated, cartoon = self._event_service.save_results() # TODO Refactor.
        self.show_image(original, annotated, cartoon)

    def show_image(self, original, annotated, cartoon, image_labels):
        # In multiprocessing mode, this method won't be called from workflow
        # Image updates would need to be handled differently (e.g., via file watching)
        self.image_original.load(str(original))
        self.image_result.load(str(cartoon))
        if self._full_capabilities:
            self.image_label.set_text(', '.join(image_labels))
        self.set_root_widget(self.main_container)

    def on_dialog_cancel(self, widget):
        self.set_root_widget(self.main_container)
    
    def on_say_pressed(self, *_):
        """Handle Say button press."""
        text = self.text_input.get_value().strip()
        if text:
            self._event_service.say(text)
            self.text_input.set_value('')  # Clear the input field.
        
    def on_back_pressed(self, *_):
        """Handle Back to Main button press."""
        self.set_root_widget(self.main_container)