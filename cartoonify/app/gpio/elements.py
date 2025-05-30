from gpiozero import *

class SmartButton(Button):
    """Specialization of gpio.Button class which does not trigger when_released
    (alias for when_deactivated) if when_held handler is defined and was called.
    """
    # FIXME Would probably break if None or multiple triggers are assigned.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.was_held = False
        self._when_deactivated = event()
        self._when_held = event()

    def __setattr__(self, key, value):
        if key in ['when_deactivated', 'when_released']:
            def f(e=None):
                if not self.was_held:
                    return value(e)
                else:
                    self.was_held = False
            super(Button, self).__setattr__(key, f)
        elif key == 'when_held':
            def f(e=None):
                retval = value(e)
                self.was_held = True
                return retval
            super(Button, self).__setattr__(key, f)
        else:
            super(Button, self).__setattr__(key, value)
