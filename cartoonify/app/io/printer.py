from __future__ import annotations
from subprocess import Popen, PIPE, check_output, run
import re
import time
from pathlib import Path

from app.debugging.logging import getLogger

from .base import BaseIODevice


class Printer(BaseIODevice):
    """Thermal printer abstraction.

    Handles printing of images and arbitrary text. Availability (enabled/disabled)
    is managed by the caller (Workflow) by either instantiating or skipping this class.
    The class itself does not gate operations via a 'no_printer' flag; callers decide.
    """

    def __init__(self, enabled: bool = True):
        BaseIODevice.__init__(self, enabled=enabled)

    def setup(self, enabled: bool | None = None):
        """Setup printer and determine availability.
        
        :param enabled: Optional override of enabled flag (None keeps constructor state).
        """
        super().setup(enabled=enabled)
        # Determine availability (simple heuristic: lp command existence could be probed later).
        # For now assume available; could add shutil.which('lp').
        self._available = True
        if not self._enabled:
            self._log.info('Printer disabled.')

    # -- Text Printing -------------------------------------------------
    def print_text(self, text: str) -> str | None:
        """Print plain text to the thermal printer.

        Returns raw lp output bytes decoded to string if a job was queued, otherwise None.
        The returned identifier can be passed to wait() for completion monitoring.
        """
        if not self._enabled:
            return None
        if not text:
            return None
        process = Popen(['lp', '-o', 'cpi=13'], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, err = process.communicate(text.encode())
        if process.returncode != 0:
            self._log.error(f"Text print failed: {err.decode().strip() if err else 'unknown error'}")
            return None
        return output.decode(errors='ignore') if output else None

    # -- Image Printing ------------------------------------------------
    def print_image(self, image_path: str | Path) -> str | None:
        """Print an image file using lp with predefined media options.

        Returns lp output (decoded) for use with wait().
        """
        if not self._enabled:
            return None
        image_path = str(image_path)
        try:
            output = check_output([
                'lp',
                '-o', 'orientation-requested=5',
                '-o', 'media=Custom.57.86x102.87mm',
                '-o', 'fit-to-page',
                image_path
            ])
            return output.decode(errors='ignore') if output else None
        except Exception as e:
            self._log.exception(f"Image print failed: {e}")
            return None

    # -- Job Monitoring -----------------------------------------------
    def wait(self, lp_output: str | None, poll_interval: float = 1.0, timeout: float | None = None) -> bool:
        """Wait until the given print job finishes.

        lp_output: Raw output from an lp command (string). If None, returns False.
        poll_interval: Seconds between lpstat polls.
        timeout: Optional max seconds to wait. None means infinite.
        Returns True if job finished (or not found), False on timeout or parse failure.
        """
        if not lp_output:
            return False
        match = re.search(r'request id is (.*) \(.*', lp_output)
        if not match:
            self._log.warning('Unable to parse print job id.')
            return False
        job_id = match.group(1)
        start = time.time()
        while True:
            result = run(['lpstat'], stdout=PIPE, stderr=PIPE, text=True)
            if not re.match(f'^{job_id}', result.stdout):
                return True
            if timeout is not None and (time.time() - start) > timeout:
                self._log.warning(f'Print job {job_id} timed out.')
                return False
            time.sleep(poll_interval)
