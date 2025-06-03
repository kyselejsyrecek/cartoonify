from gpiozero import *

class SmartButton(Button):
    """Specialization of gpio.Button class which does not trigger when_released
    (alias for when_deactivated) if when_held handler is defined and was called.
    It also blocks both handlers if any one of them is currently being processed
    and has not finished yet.
    """
    # FIXME Would probably break if None was assigned.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blocked = False
        self.was_held = False
        self._when_deactivated = event()
        self._when_held = event()

    def __setattr__(self, key, value):
        if key in ['when_deactivated', 'when_released']:
            def f(e=None):
                if not self.was_held:
                    if self.blocked:
                        return False
                    self.blocked = True
                    retval = value(e)
                    self.blocked = False
                    return retval
                else:
                    self.was_held = False
            super(Button, self).__setattr__(key, f)
        elif key == 'when_held':
            def f(e=None):
                if self.blocked:
                    return False
                self.was_held = True
                self.blocked = True
                retval = value(e)
                self.blocked = False
                return retval
            super(Button, self).__setattr__(key, f)
        else:
            super(Button, self).__setattr__(key, value)
