"""
Music Tools GUI -- FLAC to CUE Panel  v0.1
===========================================
GUI panel for flac_to_cue/flac_to_cue.py.

File picker (not folder) -> options -> Dry Run -> Apply.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QProgressBar,
    QGroupBox, QFileDialog, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QThread

from gui.theme import COLOURS

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from flac_to_cue.flac_to_cue import run_flac_to_cue
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, target, apply, skip_existing, parent=None):
        super().__init__(parent)
        self.target        = target
        self.apply         = apply
        self.skip_existing = skip_existing

    def run(self):
        try:
            result = run_flac_to_cue(
                target=self.target,
                apply=self.apply,
                skip_existing_cue=self.skip_existing,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class FlacToCuePanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_results = False
        self._worker: _Worker | None = None
        self._build_ui()
        self._set_state("idle")

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']};"
            f"border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("FLAC to CUE")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Generates a CUE sheet from MusicBrainz data for splitting single-file albums")
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(16)
        outer.addWidget(body, stretch=1)

        # File picker
        file_box = QGroupBox("Audio File")
        file_layout = QHBoxLayout(file_box)
        file_layout.setContentsMargins(12, 12, 12, 12)
        file_layout.setSpacing(8)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("Select an audio file (FLAC, WAV, MP3, etc.)...")
        self._file_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(self._file_edit, stretch=1)
        file_layout.addWidget(browse_btn)
        body_layout.addWidget(file_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(6)
        self._chk_skip = QCheckBox("Skip files that already have a .cue next to them")
        opts_layout.addWidget(self._chk_skip)
        body_layout.addWidget(opts_box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn   = QPushButton("Dry Run")
        self._apply_btn = QPushButton("Write CUE")
        self._apply_btn.setEnabled(False)
        self._run_btn.setFixedHeight(32)
        self._apply_btn.setFixedHeight(32)
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS.get('log_success', '#4ec9b0')};"
            f"color: #000; border-radius: 3px; padding: 5px 16px; min-width: 64px; }}"
            f"QPushButton:hover {{ background: #5edfc0; }}"
            f"QPushButton:disabled {{ background: {COLOURS['disabled_bg']};"
            f"color: {COLOURS['disabled_text']}; }}"
        )
        self._run_btn.clicked.connect(self._on_run)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._apply_btn)
        btn_row.addStretch()
        body_layout.addLayout(btn_row)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {COLOURS['border']}; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {COLOURS['accent']}; border-radius: 3px; }}"
        )
        body_layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._status_lbl)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        self._summary_lbl.setWordWrap(True)
        body_layout.addWidget(self._summary_lbl)

        body_layout.addStretch()

    def _set_state(self, state: str):
        if state == "idle":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Dry Run")
            self._apply_btn.setEnabled(False)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._run_btn.setEnabled(False)
            self._apply_btn.setEnabled(False)
        elif state == "done_dry":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Re-run Dry Run")
            self._apply_btn.setEnabled(self._has_results)
            self._status_lbl.setText("")
        elif state == "done_apply":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Dry Run")
            self._apply_btn.setEnabled(False)
            self._status_lbl.setText("")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio file",
            str(Path.home()),
            "Audio Files (*.flac *.wav *.mp3 *.m4a *.ogg *.aiff);;All Files (*)",
        )
        if path:
            self._file_edit.setText(path)
            self._set_state("idle")
            self._summary_lbl.setText("")

    def _on_run(self):
        if not self._file_edit.text().strip():
            self.log_message.emit("FLAC to CUE: no file selected.", "warning")
            return
        self._start_worker(apply=False)

    def _on_apply(self):
        self._start_worker(apply=True)

    def _start_worker(self, apply: bool):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "FLAC to CUE: script not found — check project structure.", "error"
            )
            return
        target = self._file_edit.text().strip()
        self._set_state("running")
        self._progress.setValue(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Writing CUE..." if apply else "Looking up on MusicBrainz...")
        self.log_message.emit(
            f"FLAC to CUE: {'apply' if apply else 'dry run'} — {Path(target).name}", "info"
        )
        self._worker = _Worker(
            target, apply,
            skip_existing=self._chk_skip.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(lambda r: self._on_finished(r, apply))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status_lbl.setText(message)

    def _on_finished(self, result: dict, was_apply: bool):
        tracks = result.get("tracks", 0)
        cue    = result.get("cue_path", result.get("report_path", ""))
        status = result.get("status", "")

        self._has_results = bool(tracks)

        if was_apply:
            summary = f"CUE written: {cue}" if cue else f"Status: {status}"
            level = "success"
            self._set_state("done_apply")
        else:
            summary = f"Tracks found: {tracks}  |  Status: {status}"
            level = "info"
            self._set_state("done_dry")

        self._progress.setValue(100)
        self._summary_lbl.setText(summary)
        self.log_message.emit(
            f"FLAC to CUE {'complete' if was_apply else 'dry run'} — {summary}", level
        )

    def _on_error(self, message: str):
        self.log_message.emit(f"FLAC to CUE error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")
