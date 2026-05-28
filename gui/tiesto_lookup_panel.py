"""
tiesto_lookup_panel.py — GUI panel for tiesto_lookup.py
Tiesto collection lookup tuned for "Year - Artist - Title [CatNo]" folder format.
"""
from __future__ import annotations

from gui._lookup_base import MBLookupBasePanel
from anjuna_mb_lookup.tiesto_lookup import run_tiesto_lookup


class TiestoLookupPanel(MBLookupBasePanel):
    _TITLE = "Tiesto Lookup"

    def _run_fn(self):
        return run_tiesto_lookup
