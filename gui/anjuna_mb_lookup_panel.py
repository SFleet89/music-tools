"""
anjuna_mb_lookup_panel.py — GUI panel for anjuna_mb_lookup.py
Anjuna-specific MusicBrainz lookup using ANJ*/ANJCD* catalogue numbers.
"""
from __future__ import annotations

from gui._lookup_base import MBLookupBasePanel
from anjuna_mb_lookup.anjuna_mb_lookup import run_anjuna_mb_lookup


class AnjunaMBLookupPanel(MBLookupBasePanel):
    _TITLE = "Anjuna MB Lookup"

    def _run_fn(self):
        return run_anjuna_mb_lookup
