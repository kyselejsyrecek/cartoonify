import remi.gui as gui
from remi import App
import PIL.Image
import io
import time
from pathlib import Path
import importlib
import logging
import sys


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


def get_WebGui(workflow, cam_only):
    class WebGui(App):
        """
        gui for the app
        """

        app = workflow
        full_capabilities = not cam_only
        _logger = logging.getLogger("WebGui")

        def __init__(self, *args):
            super().__init__(*args)

        def idle(self):
            # idle function called every update cycle
            pass

        def main(self):
            self.display_original = False
            #self.display_tagged = False # TODO Not yet implemented.
            ui = self.construct_ui()
            self.app.connect_web_gui(self)
            return ui

        def construct_ui(self):
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
            button_snap = gui.Button('snap')
            button_snap.style['margin'] = "0px"
            button_snap.style['overflow'] = "auto"
            button_snap.style['width'] = "200px"
            button_snap.style['height'] = "30px"
            hbox_snap.append(button_snap, 'button_snap')
            if self.full_capabilities:
                button_open = gui.Button('open image from file')
                button_open.style['margin'] = "0px"
                button_open.style['overflow'] = "auto"
                button_open.style['width'] = "200px"
                button_open.style['height'] = "30px"
                hbox_snap.append(button_open, 'button_open')
            vbox_settings = gui.VBox()
            vbox_settings.style['order'] = "4349486136"
            vbox_settings.style['display'] = "flex"
            vbox_settings.style['overflow'] = "auto"
            vbox_settings.style['width'] = "250px"
            vbox_settings.style['flex-direction'] = "column"
            vbox_settings.style['position'] = "static"
            vbox_settings.style['justify-content'] = "space-around"
            vbox_settings.style['-webkit-order'] = "4349486136"
            vbox_settings.style['margin'] = "0px"
            vbox_settings.style['align-items'] = "center"
            vbox_settings.style['top'] = "149.734375px"
            vbox_settings.style['height'] = "80px"
            checkbox_display_original = gui.CheckBoxLabel(' Display original image', False, '')
            checkbox_display_original.style['margin'] = "0px"
            checkbox_display_original.style['align-items'] = "center"
            checkbox_display_original.style['width'] = "200px"
            checkbox_display_original.style['top'] = "135.734375px"
            checkbox_display_original.style['position'] = "static"
            checkbox_display_original.style['height'] = "30px"
            vbox_settings.append(checkbox_display_original, 'checkbox_display_original')
            #checkbox_display_tagged = gui.CheckBoxLabel(' Display tagged image', False, '')
            #checkbox_display_tagged.style['margin'] = "0px"
            #checkbox_display_tagged.style['width'] = "200px"
            #checkbox_display_tagged.style['top'] = "135px"
            #checkbox_display_tagged.style['position'] = "static"
            #checkbox_display_tagged.style['height'] = "30px"
            #vbox_settings.append(checkbox_display_tagged, 'checkbox_display_tagged')
            hbox_snap.append(vbox_settings, 'vbox_settings')
            if self.full_capabilities:
                button_close = gui.Button('close')
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
            if self.full_capabilities:
                self.image_label = gui.Label('', width=400, height=30, margin='10px')
                self.image_label.style['text-align'] = "center"
                self.main_container.append(self.image_label, 'image_label')

            # event handlers
            button_snap.set_on_click_listener(self.on_snap_pressed)
            if self.full_capabilities:
                button_open.set_on_click_listener(self.on_open_pressed)
                button_close.set_on_click_listener(self.on_close_pressed)
            checkbox_display_original.set_on_change_listener(self.on_display_original_change)
            #checkbox_display_tagged.set_on_change_listener(self.on_display_tagged_change)

            return self.main_container

        def on_display_original_change(self, widget, value):
            self.display_original = value
            self.image_original.style['display'] = "block" if self.display_original else "none"

        #def on_display_tagged_change(self, widget, value):
        #    self.display_tagged = value

        def on_close_pressed(self, *_):
            self.app.close()
            self.close()  #closes the application
            # sys.exit()

        def on_snap_pressed(self, *_):
            # FIXME Seems to be sometimes still called with a delay when another print operation is in progress.
            self.app.capture_event() 

        def on_open_pressed(self, *_):
            self.fileselectionDialog = gui.FileSelectionDialog('File Selection Dialog', 'Select an image file', False, '.')
            self.fileselectionDialog.set_on_confirm_value_listener(
                self.process_image)
            self.fileselectionDialog.set_on_cancel_dialog_listener(
                self.on_dialog_cancel)
            # here is shown the dialog as root widget
            self.fileselectionDialog.show(self)

        def process_image(self, widget, file_list):
            if len(file_list) != 1:
                return
            original = file_list[0]
            self.app.process(original)
            annotated, cartoon = self.app.save_results() # TODO Refactor.
            self.show_image(original, annotated, cartoon)

        def show_image(self, original, annotated, cartoon, image_labels):
            self.image_original.load(str(original))
            self.image_result.load(str(cartoon))
            if self.full_capabilities:
                self.image_label.set_text(', '.join(image_labels))
            self.set_root_widget(self.main_container)

        def on_dialog_cancel(self, widget):
            self.set_root_widget(self.main_container)

    return WebGui