"""
Main GUI for Cartoonify Application

This module contains the main user interface for capturing and processing images.
"""

import remi.gui as gui
import PIL.Image
import io
import time
from pathlib import Path

from app.debugging.logging import getLogger


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
            file_path_name (str): Path to image file
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
            update_index: Cache busting parameter
            
        Returns:
            tuple: (data, headers) or None
        """
        if self._buf is None:
            return None
        self._buf.seek(0)
        headers = {'Content-type': 'image/png'}
        return [self._buf.read(), headers]


def build_main_ui(app, event_service, logger, exit_event, halt_event, i18n, cam_only):
    """Build the main camera/capture UI.
    
    This is a standalone builder function that creates the main UI without
    being tied to a specific App class. This allows it to be used with the
    router pattern.
    
    Args:
        app: REMI App instance (RouterApp)
        event_service: Event service for application events
        logger: Logger instance
        exit_event: Event for application exit
        halt_event: Event for system halt
        i18n: Internationalization helper
        cam_only: Whether to show only camera functionality
        
    Returns:
        gui.Widget: The constructed UI
    """
    log = logger
    _ = i18n.gettext
    full_capabilities = not cam_only
    
    # Store references in app for event handlers.
    app._event_service = event_service
    app._log = logger
    app._exit_event = exit_event
    app._halt_event = halt_event
    app._i18n = i18n
    app._full_capabilities = full_capabilities
    app.display_original = False
    
    log.debug('Building main UI')
    
    # Layout.
    main_container = gui.VBox()
    main_container.style.update({
        'top': '0px',
        'display': 'flex',
        'overflow': 'auto',
        'width': '100%',
        'flex-direction': 'column',
        'position': 'absolute',
        'justify-content': 'space-around',
        'margin': '0px',
        'align-items': 'center',
        'left': '0px',
        'height': '100%'
    })
    
    # Control buttons box.
    hbox_snap = gui.HBox()
    hbox_snap.style.update({
        'left': '0px',
        'display': 'flex',
        'overflow': 'auto',
        'width': '70%',
        'flex-direction': 'row',
        'position': 'static',
        'justify-content': 'space-around',
        'margin': '0px',
        'align-items': 'center',
        'height': '150px'
    })
    
    # Snap button.
    button_snap = gui.Button(_('Snap'))
    button_snap.style.update({
        'margin': '0px',
        'overflow': 'auto',
        'width': '200px',
        'height': '30px'
    })
    hbox_snap.append(button_snap, 'button_snap')
    
    # Open image button (only if full capabilities).
    if full_capabilities:
        button_open = gui.Button(_('Open image'))
        button_open.style.update({
            'margin': '0px',
            'overflow': 'auto',
            'width': '200px',
            'height': '30px'
        })
        hbox_snap.append(button_open, 'button_open')
    
    # Settings box.
    vbox_settings = gui.VBox()
    vbox_settings.style.update({
        'display': 'flex',
        'width': '250px',
        'flex-direction': 'column',
        'position': 'static',
        'justify-content': 'space-around',
        'margin': '0px',
        'align-items': 'center',
        'height': '80px'
    })
    
    # Display original checkbox.
    checkbox_display_original = gui.CheckBoxLabel(_(' Display original image'), False, '')
    checkbox_display_original.style.update({
        'margin': '0px',
        'margin-left': '35px',
        'align-items': 'center',
        'width': '200px',
        'position': 'static',
        'height': '30px'
    })
    vbox_settings.append(checkbox_display_original, 'checkbox_display_original')
    hbox_snap.append(vbox_settings, 'vbox_settings')
    
    # Close button (only if full capabilities).
    if full_capabilities:
        button_close = gui.Button(_('Terminate'))
        button_close.style.update({
            'background-color': 'red',
            'width': '200px',
            'height': '30px'
        })
        hbox_snap.append(button_close, 'button_close')
    
    main_container.append(hbox_snap, 'hbox_snap')
    
    # Image viewers.
    height = 300
    image_original = PILImageViewerWidget(height=height)
    image_original.style['display'] = 'none'  # Hidden by default.
    main_container.append(image_original, 'image_original')
    
    image_result = PILImageViewerWidget(height=height)
    main_container.append(image_result, 'image_result')
    
    # Image label (only if full capabilities).
    if full_capabilities:
        image_label = gui.Label('', width=400, height=30, margin='10px')
        image_label.style['text-align'] = 'center'
        main_container.append(image_label, 'image_label')
    
    # Store widget references in app for later access.
    app.main_container = main_container
    app.image_original = image_original
    app.image_result = image_result
    if full_capabilities:
        app.image_label = image_label
    
    # Event handlers.
    def on_snap_pressed(*_):
        event_service.capture()
    
    def on_open_pressed(*_):
        fileselectionDialog = gui.FileSelectionDialog(
            _('File Selection Dialog'),
            _('Select an image file'),
            False,
            '.'
        )
        
        def process_image(widget, file_list):
            if len(file_list) != 1:
                return
            original = file_list[0]
            event_service.process(original)
            annotated, cartoon = event_service.save_results()
            # Update images.
            image_original.load(str(original))
            image_result.load(str(cartoon))
            if full_capabilities:
                # Note: image_labels would need to be passed from save_results.
                pass
        
        def on_dialog_cancel(widget):
            app.set_root_widget(main_container)
        
        fileselectionDialog.onchange.do(process_image)
        fileselectionDialog.set_on_cancel_dialog_listener(on_dialog_cancel)
        fileselectionDialog.show(app)
    
    def on_close_pressed(*_):
        event_service.close()
        app.close()
    
    def on_display_original_change(widget, value):
        app.display_original = value
        image_original.style['display'] = 'block' if value else 'none'
    
    # Connect events.
    button_snap.onclick.do(on_snap_pressed)
    if full_capabilities:
        button_open.onclick.do(on_open_pressed)
        button_close.onclick.do(on_close_pressed)
    checkbox_display_original.onchange.do(on_display_original_change)
    
    return main_container


def show_image_on_app(app, original, annotated, cartoon, image_labels):
    """Update the displayed images on the app.
    
    This function can be called from the workflow to update images.
    
    Args:
        app: REMI App instance with image widgets
        original (str): Path to original image
        annotated (str): Path to annotated image
        cartoon (str): Path to cartoon image
        image_labels (list): List of detected object labels
    """
    if hasattr(app, 'image_original') and app.image_original:
        app.image_original.load(str(original))
    
    if hasattr(app, 'image_result') and app.image_result:
        app.image_result.load(str(cartoon))
    
    if hasattr(app, 'image_label') and app.image_label:
        app.image_label.set_text(', '.join(image_labels))
    
    if hasattr(app, 'main_container') and app.main_container:
        app.set_root_widget(app.main_container)
