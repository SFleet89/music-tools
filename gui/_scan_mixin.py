"""
_scan_mixin.py  --  shared scan-timer mixin for Music Tools GUI panels
=======================================================================
Provides a live elapsed-time ticker and indeterminate / determinate
progress-bar switching for any panel that has a long-running scan.

Usage
-----
1.  Inherit from ScanTimerMixin (before QWidget):

        class MyPanel(ScanTimerMixin, QWidget):

2.  Call ``_scan_mixin_init()`` in ``__init__`` *after* ``super().__init__``
    but *before* ``_build_ui()`` / ``_set_state()``:

        def __init__(self, parent=None):
            super().__init__(parent)
            self._scan_mixin_init()
            self._build_ui()

3.  Call ``_start_scan_timer()`` when a scan begins (in _set_state("running")
    or directly in _on_run / _start_worker).

4.  Call ``_stop_scan_timer()`` when the scan ends (done, error, or idle reset).

5.  Connect the worker's progress signal to ``_on_scan_progress`` directly,
    OR keep a thin ``_on_progress`` that delegates here::

        def _on_progress(self, current, total, message):
            self._on_scan_progress(current, total, message)

Attributes managed by this mixin
---------------------------------
_elapsed_secs   int      seconds since scan started
_current_phase  str      phase label shown in status bar
_timer          QTimer   1-second tick connected to _tick_elapsed()

Required panel attributes (must already exist when mixin methods run)
---------------------------------------------------------------------
self._progress   QProgressBar
self._status_lbl QLabel
"""

from __future__ import annotations

from PySide6.QtCore import QTimer


class ScanTimerMixin:
    """
    Mixin that adds a live elapsed-time ticker and indeterminate /
    determinate progress-bar handling to scanning panels.

    Panels must have ``_progress`` (QProgressBar) and
    ``_status_lbl`` (QLabel) as instance attributes.
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _scan_mixin_init(self) -> None:
        """Set up mixin state.  Call once from the panel's ``__init__``."""
        self._elapsed_secs: int = 0
        self._current_phase: str = ""
        self._timer: QTimer = QTimer(self)
        self._timer.timeout.connect(self._tick_elapsed)

    # ------------------------------------------------------------------
    # Timer control
    # ------------------------------------------------------------------

    def _start_scan_timer(self) -> None:
        """Reset elapsed time, switch bar to indeterminate, start ticking."""
        self._elapsed_secs = 0
        self._current_phase = "Starting…"
        self._progress.setRange(0, 0)   # animated pulse (indeterminate)
        self._timer.start(1000)

    def _stop_scan_timer(self) -> None:
        """Stop ticking and restore bar to determinate mode."""
        self._timer.stop()
        self._progress.setRange(0, 100)

    # ------------------------------------------------------------------
    # Tick / format
    # ------------------------------------------------------------------

    def _tick_elapsed(self) -> None:
        """Called every second by the QTimer to refresh the status label."""
        self._elapsed_secs += 1
        self._status_lbl.setText(
            f"{self._current_phase}  {self._fmt_elapsed(self._elapsed_secs)}"
        )

    @staticmethod
    def _fmt_elapsed(secs: int) -> str:
        """Return a compact elapsed-time string: ``(42s)`` or ``(1m 07s)``."""
        if secs < 60:
            return f"({secs}s)"
        m, s = divmod(secs, 60)
        return f"({m}m {s:02d}s)"

    # ------------------------------------------------------------------
    # Standard progress handler
    # ------------------------------------------------------------------

    def _on_scan_progress(self, current: int, total: int, message: str) -> None:
        """
        Standard handler for the worker ``progress(int, int, str)`` signal.

        - ``total > 0`` → determinate bar showing percentage;
          status = ``"<message>  [current / total]  (elapsed)"``
        - ``total == 0`` → indeterminate bar (animated pulse);
          status = ``"<message>  (elapsed)"``
        """
        elapsed = self._fmt_elapsed(self._elapsed_secs)
        if total > 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(int(current / total * 100))
            self._current_phase = (
                f"{message}  [{current:,} / {total:,}]"
                if message else f"[{current:,} / {total:,}]"
            )
        else:
            self._progress.setRange(0, 0)
            self._current_phase = message or "Scanning…"
        self._status_lbl.setText(f"{self._current_phase}  {elapsed}")
