"""
anjuna_tagger_panel.py — GUI panel for anjuna_tagger.py
Tags album folders using output from anjuna_mb_lookup.py.
"""
from __future__ import annotations

from gui._tagger_base import TaggerBasePanel
from anjuna_mb_lookup.anjuna_tagger import run_anjuna_tagger


class AnjunaTaggerPanel(TaggerBasePanel):
    _TITLE = "Anjuna Tagger"

    def _run_fn(self):
        return run_anjuna_tagger
