"""
mb_lookup_panel.py — GUI panel for mb_lookup.py
General-purpose MusicBrainz lookup with optional fingerprinting.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QCheckBox

from gui._lookup_base import MBLookupBasePanel
from anjuna_mb_lookup.mb_lookup import run_mb_lookup


class MBLookupPanel(MBLookupBasePanel):
    _TITLE = "MB Lookup"

    def _extra_options(self, row: QHBoxLayout):
        self._no_fp_chk = QCheckBox("Skip fingerprinting")
        row.addWidget(self._no_fp_chk)

    def _extra_kwargs(self) -> dict:
        return {"no_fingerprint": self._no_fp_chk.isChecked()}

    def _run_fn(self):
        return run_mb_lookup
