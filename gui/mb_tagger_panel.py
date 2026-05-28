"""
mb_tagger_panel.py — GUI panel for mb_tagger.py
Tags album folders using output from mb_lookup.py or any lookup CSV.
"""
from __future__ import annotations

from gui._tagger_base import TaggerBasePanel
from anjuna_mb_lookup.mb_tagger import run_mb_tagger


class MBTaggerPanel(TaggerBasePanel):
    _TITLE = "MB Tagger"

    def _run_fn(self):
        return run_mb_tagger
