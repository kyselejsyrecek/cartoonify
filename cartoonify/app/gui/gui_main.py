"""
Main GUI Application

This module contains the main camera/capture interface accessible at the root path (/).
"""

import remi.gui as gui
import PIL.Image
import io
import time
from pathlib import Path
from remi import App


class PILImageViewerWidget(gui.Image):
    """Widget for displaying PIL images in REMI GUI."""
    
    def __init__(self, **kwargs):
        super(PILImageViewerWidget, self).__init__(**kwargs)
        self._buf = None
        initial_image = str(Path(__file__).parent / '..' / '..' / 'images' / 'default.png')
        self.load(initial_image)

    def load(self, file_path_name):
        """Load image from file path.
        
        Args:
            file_path_name (str): Path to image file.
        """
        pil_image = PIL.Image.open(file_path_name)
        self._buf = io.BytesIO()
        pil_image.save(self._buf, format='png')
        self.refresh()

    def refresh(self):
        """Refresh the image display with cache busting."""
        i = int(time.time() * 1e6)
        self.attributes['src'] = "/%s/get_image_data?update_index=%d" % (id(self), i)

    def get_image_data(self, update_index):
        """Get image data for HTTP response.
        
        Args:
            update_index: Cache busting parameter.
            
        Returns:
            tuple: (data, headers) or None.
        """
        if self._buf is None:
            return None
        self._buf.seek(0)
        headers = {'Content-type': 'image/png'}
        return [self._buf.read(), headers]


class MainGui(App):
    """
    Main GUI for camera/capture interface.
    
    This App displays the camera interface with:
    - Snap button (capture photo).
    - Open button (load image from file).
    - Terminate button (close app).
    - Image display widgets.
    - Settings checkboxes.
    """
    
    _event_service = None
    _log = None
    _i18n = None
    _full_capabilities = True
    _exit_event = None
    _halt_event = None
    
    def __init__(self, *args):
        """Initialize MainGui.
        
        Args:
            *args: Userdata tuple (event_service, logger, exit_event, halt_event, i18n, cam_only).
        """
        super().__init__(*args)
        
    def idle(self):
        """Idle callback called periodically by REMI.
        
        Checks for exit events and performs cleanup.
        """
        try:
            if hasattr(self, '_exit_event') and self._exit_event and self._exit_event.is_set():
                if self._log:
                    self._log.info('Exit event detected in MainGui - closing application.')
                self.close()
        except Exception as e:
            if hasattr(self, '_log') and self._log:
                self._log.warning(f'Could not check exit_event in MainGui: {e}')
    
    def main(self, event_service, logger, exit_event, halt_event, i18n, cam_only):
        """Main entry point for MainGui.
        
        Args:
            event_service: Event service proxy for inter-process communication.
            logger: Logger instance.
            exit_event: Event for application exit.
            halt_event: Event for system halt.
            i18n: Internationalization helper.
            cam_only: Boolean flag for camera-only mode.
        
        Returns:
            Widget: The root widget for this App.
        """
        self._event_service = event_service
        self._log = logger
        self._exit_event = exit_event
        self._halt_event = halt_event
        self._i18n = i18n
        self._full_capabilities = not cam_only
        
        self._log.debug(f'MainGui.main() called, path={getattr(self, "path", "unknown")}')
        
        self.display_original = False
        return self.construct_ui()
    
    def construct_ui(self):
        """Construct the main UI.
        
        Returns:
            Widget: The main container widget.
        """
        self._log.debug('Constructing Main UI')
        _ = self._i18n.gettext
        
        # Layout.
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

        # Event handlers.
        button_snap.onclick.do(self.on_snap_pressed)
        if self._full_capabilities:
            button_open.onclick.do(self.on_open_pressed)
            button_close.onclick.do(self.on_close_pressed)
        checkbox_display_original.onchange.do(self.on_display_original_change)

        return self.main_container
    
    def on_display_original_change(self, widget, value):
        """Handle display original checkbox change.
        
        Args:
            widget: The checkbox widget.
            value: Boolean checkbox value.
        """
        self.display_original = value
        self.image_original.style['display'] = "block" if self.display_original else "none"

    def on_close_pressed(self, *_):
        """Handle Terminate button press."""
        self._event_service.close()
        self.close()

    def on_snap_pressed(self, *_):
        """Handle Snap button press."""
        self._event_service.capture()

    def on_open_pressed(self, *_):
        """Handle Open button press."""
        _ = self._i18n.gettext
        self.fileselectionDialog = gui.FileSelectionDialog(
            _('File Selection Dialog'), 
            _('Select an image file'), 
            False, 
            '.'
        )
        self.fileselectionDialog.onchange.do(self.process_image)
        self.fileselectionDialog.set_on_cancel_dialog_listener(self.on_dialog_cancel)
        self.fileselectionDialog.show(self)

    def process_image(self, widget, file_list):
        """Process selected image file.
        
        Args:
            widget: The file selection dialog widget.
            file_list: List of selected file paths.
        """
        if len(file_list) != 1:
            return
        original = file_list[0]
        self._event_service.process(original)
        annotated, cartoon = self._event_service.save_results()
        self.show_image(original, annotated, cartoon, [])

    def show_image(self, original, annotated, cartoon, image_labels):
        """Update displayed images.
        
        Args:
            original (str): Path to original image.
            annotated (str): Path to annotated image.
            cartoon (str): Path to cartoon image.
            image_labels (list): List of detected object labels.
        """
        self.image_original.load(str(original))
        self.image_result.load(str(cartoon))
        if self._full_capabilities and hasattr(self, 'image_label'):
            self.image_label.set_text(', '.join(image_labels))
        self.set_root_widget(self.main_container)

    def on_dialog_cancel(self, widget):
        """Handle file selection dialog cancel.
        
        Args:
            widget: The dialog widget.
        """
        self.set_root_widget(self.main_container)
