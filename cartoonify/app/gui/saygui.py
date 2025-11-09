"""
Text-to-Speech GUI for Cartoonify Application

This module contains the text-to-speech interface accessible at /say path.
"""

import remi.gui as gui
from app.gui.remi_multipath import create_nav_button


def build_say_ui(app, event_service, logger, exit_event, halt_event, i18n, cam_only):
    """Build the text-to-speech UI.
    
    This is a standalone builder function that creates the TTS UI without
    being tied to a specific App class.
    
    Args:
        app: REMI App instance (RouterApp)
        event_service: Event service for TTS functionality
        logger: Logger instance
        exit_event: Event for application exit
        halt_event: Event for system halt
        i18n: Internationalization helper
        cam_only: Not used in this UI
        
    Returns:
        gui.Widget: The constructed UI
    """
    log = logger
    _ = i18n.gettext
    
    # Store references in app.
    app._event_service = event_service
    app._log = logger
    app._i18n = i18n
    
    log.debug('Building Say UI')
    
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
        'font-size': '28px',
        'font-weight': 'bold',
        'margin': '30px 20px 20px 20px',
        'color': '#333',
        'text-align': 'center'
    })
    main_container.append(title, 'title')
    
    # Form container.
    form_container = gui.VBox()
    form_container.style.update({
        'background-color': 'white',
        'padding': '40px',
        'border-radius': '12px',
        'box-shadow': '0 4px 20px rgba(0,0,0,0.1)',
        'width': '80%',
        'max-width': '700px',
        'margin': '20px'
    })
    
    # Instruction label.
    instruction = gui.Label(_('Enter text below and press Say to hear it spoken:'))
    instruction.style.update({
        'margin-bottom': '15px',
        'font-size': '16px',
        'color': '#555',
        'text-align': 'center'
    })
    form_container.append(instruction, 'instruction')
    
    # Text input field.
    text_input = gui.TextInput()
    text_input.attributes['placeholder'] = _('Type something to say...')
    text_input.style.update({
        'width': '100%',
        'padding': '15px',
        'font-size': '18px',
        'border': '2px solid #ddd',
        'border-radius': '8px',
        'margin-bottom': '25px',
        'box-sizing': 'border-box',
        'font-family': 'Arial, sans-serif'
    })
    form_container.append(text_input, 'text_input')
    
    # Button container.
    button_container = gui.HBox()
    button_container.style.update({
        'display': 'flex',
        'justify-content': 'center',
        'gap': '15px',
        'flex-wrap': 'wrap'
    })
    
    # Say button.
    say_button = gui.Button(_('Say'))
    say_button.style.update({
        'padding': '15px 40px',
        'font-size': '18px',
        'font-weight': 'bold',
        'background-color': '#4CAF50',
        'color': 'white',
        'border': 'none',
        'border-radius': '8px',
        'cursor': 'pointer',
        'min-width': '150px',
        'transition': 'background-color 0.3s'
    })
    
    # Clear button.
    clear_button = gui.Button(_('Clear'))
    clear_button.style.update({
        'padding': '15px 40px',
        'font-size': '18px',
        'font-weight': 'bold',
        'background-color': '#FF9800',
        'color': 'white',
        'border': 'none',
        'border-radius': '8px',
        'cursor': 'pointer',
        'min-width': '150px',
        'transition': 'background-color 0.3s'
    })
    
    # Back button using router navigation.
    back_button = create_nav_button(
        app,
        _('Back to Main'),
        '/',
        **{
            'padding': '15px 40px',
            'font-size': '18px',
            'font-weight': 'bold',
            'background-color': '#2196F3',
            'color': 'white',
            'border': 'none',
            'border-radius': '8px',
            'cursor': 'pointer',
            'min-width': '150px',
            'transition': 'background-color 0.3s'
        }
    )
    
    button_container.append(say_button, 'say_button')
    button_container.append(clear_button, 'clear_button')
    button_container.append(back_button, 'back_button')
    
    form_container.append(button_container, 'button_container')
    
    # Status label.
    status_label = gui.Label('')
    status_label.style.update({
        'margin-top': '20px',
        'font-size': '14px',
        'color': '#666',
        'text-align': 'center',
        'min-height': '20px'
    })
    form_container.append(status_label, 'status_label')
    
    main_container.append(form_container, 'form_container')
    
    # Event handlers.
    def on_say_pressed(widget):
        """Handle Say button press."""
        text = text_input.get_value().strip()
        if text:
            log.info(f'TTS requested: {text}')
            event_service.say(text)
            status_label.set_text(_('Speaking...'))
            # Clear status after a moment would require a timer.
        else:
            status_label.set_text(_('Please enter some text first.'))
    
    def on_clear_pressed(widget):
        """Handle Clear button press."""
        text_input.set_value('')
        status_label.set_text(_('Text cleared.'))
    
    # Connect events.
    say_button.onclick.do(on_say_pressed)
    clear_button.onclick.do(on_clear_pressed)
    
    return main_container
