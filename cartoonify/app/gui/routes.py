"""
Routes configuration for WebGui proxy.

Maps URL paths to their corresponding GUI application classes.
"""

from .app import MainWebGui, SayWebGui


routes = {
    '/': {
        'gui_class': MainWebGui,
        'description': 'Main camera/capture interface'
    },
    '/say': {
        'gui_class': SayWebGui,
        'description': 'Text-to-speech interface'
    }
}
