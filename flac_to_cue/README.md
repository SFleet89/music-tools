# MusicBrainz Tagger Tools

A set of scripts for batch-tagging music folders using MusicBrainz data. Looks up releases by audio fingerprint, catalogue number, artist, or title — scores candidates using file metadata for confidence — then writes full tags and embeds cover art.

Nothing is changed until you run with `--apply`. Dry run by default.

---

## Scripts

| Script | Purpose |
|---|---|
| `anjuna_mb_lookup.py` | Anjuna-specific lookup — extracts ANJ*/ANJCD* catalogue numbers from folder names |
| `mb_lookup.py` | General-purpose lookup — works with any collection, any folder naming convention |
| `tiesto_lookup.py` | Tiesto collection lookup — same as mb_lookup v1.0, tuned for `Year - Artist - Title [CatNo]` format |
| `anjuna_tagger.py` | Tags files using output from `anjuna_mb_lookup.py` |
| `mb_tagger.py` | Tags files using output from `mb_lookup.py` or any lookup CSV |
| `tagger_undo.py` | Reverses folder renames made by the taggers (file tags are not undone) |
| `rename_to_catno.py` | Renames tagged album folders to `CATNO - Album Name` format using embedded tags |
| `rename_undo.py` | Reverses folder renames made by `rename_to_catno.py` |
| `fix_featuring.py` | Moves featuring credits from Artist tag to Title tag across all audio files |
| `flac_to_cue.py` | Generates a CUE sheet for an audio file (FLAC, WAV, AIFF, MP3, M4A, OGG) using MusicBrainz data, for splitting with CUETools |
| `move_from_report.py` | Moves review/no-match folders using an existing CSV report, without re-running the lookup |
| `anjuna_lookup_viewer.html` | Interactive viewer for all lookup CSVs — review and select correct releases |

---

## Requirements

```
pip install mutagen
```

**For fingerprinting** — place `fpcalc.exe` (Chromaprint) in the shared tools folder:
```
C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\fpcalc.exe
```
Or pass a custom path with `--fpcalc`. If fpcalc is not found, the script continues without fingerprinting.

---

## Workflow

### Anjunabeats collection

```
# 1. Look up releases by ANJ catalogue number
python anjuna_mb_lookup.py

# 2. Open CSV in anjuna_lookup_viewer.html, review, export with selections

# 3. Dry run — preview tags and new folder names
python anjuna_tagger.py

# 4. Tag for real
python anjuna_tagger.py --apply

# Optional: undo folder renames if something went wrong
python tagger_undo.py           # dry run — preview what would be undone
python tagger_undo.py --apply   # execute undo
```

### Any other collection

```
# 1. Look up releases (fingerprint + catno + metadata fallbacks)
python mb_lookup.py

# 2. Optionally move review/no-match folders for easier sorting
#    Option A — move immediately after the lookup run:
python mb_lookup.py --move          # dry run — see what would move
python mb_lookup.py --move --apply  # execute moves

#    Option B — move later from an existing report:
python move_from_report.py                    # file picker
python move_from_report.py --apply            # file picker, execute moves

# 3. Open CSV in anjuna_lookup_viewer.html, review, export with selections

# 4. Dry run
python mb_tagger.py

# 5. Tag for real
python mb_tagger.py --apply

# Optional: undo folder renames if something went wrong
python tagger_undo.py --apply
```

### Audio to CUE (single large audio file → split tracks)

For releases where you have one audio file per disc (FLAC, WAV, AIFF, MP3,
M4A, or OGG) but no CUE sheet. Dry run by default — use `--apply` to write.

```
# Dry run — resolves MB matches and shows CUE previews, nothing written
python flac_to_cue.py --pick

# Write CUE sheets (confirms each file before writing)
python flac_to_cue.py --pick --apply

# Recursive scan of a folder (skips files that already have a .cue)
python flac_to_cue.py --scan --apply

# Untagged WAV — provide the MusicBrainz URL directly (dry run)
python flac_to_cue.py --url "https://musicbrainz.org/release/<uuid>" --pick

# Untagged WAV — provide URL + path, write CUE
python flac_to_cue.py --url "https://musicbrainz.org/release/<uuid>" --path "CD1.wav" --apply

# Multi-disc untagged WAVs in one folder — point --path at the folder
python flac_to_cue.py --url "https://musicbrainz.org/release/<uuid>" --path "C:\album\" --apply

# Then open each .cue in CUETools to split into individual tracks
# CUETools will look for the matching audio file in the same folder automatically
```

**`--url` flag:** Use this when the auto-lookup fails or when you have a completely
untagged WAV file. Copy the release URL from MusicBrainz and pass it with `--url`.
The MBID is extracted from the URL and the full tag-reading and search fallback chain
are bypassed. Everything else (dry-run, confirmation, reports, multi-disc matching)
works as normal.

**Launchers:**
- `Run - FLAC to CUE (Dry Run).cmd` — opens picker, shows matches without writing
- `Run - FLAC to CUE (Apply).cmd`  — opens picker, confirms and writes CUE files

---

## How mb_lookup.py finds releases

For each subfolder it tries these strategies in order, stopping as soon as results are found:

| Priority | Method | Notes |
|---|---|---|
| 0 | **AcoustID fingerprint** | Samples up to 3 files, queries AcoustID, ranks MB release IDs by consensus |
| 1 | **Catalogue number** | Extracted from `[brackets]` in folder name |
| 2 | **Artist + Title** | Parsed from `Artist - Title` structure in folder name |
| 3 | **Title only** | In case artist name doesn't match MB exactly |
| 4 | **Album tag from files** | Reads album tag from embedded file metadata as last resort |

### Folder name formats supported

```
1999 - DJ Tiesto - Sparkles [BH 118-5] WEB
2001 - DJ Tiesto - Flight 643 [Magik Muzik 801-1] CD
Above & Beyond - Sun & Moon [ANJ196D] (2011)
Kesha - Animal + Cannibal (15th Anniversary)
Artist - Album Title (Year)
Artist - Album Title
jeremy-soule-the-elder-scrolls-v-skyrim   ← falls back to file tags
```

---

## Scoring

Each candidate release is scored against your folder to rank results:

| Column | What it measures |
|---|---|
| `search_score` | How well the MB catalogue number / title matches your folder name |
| `meta_score` | How well the MB tracklist matches your local file tags |
| `combined_score` | Weighted average: search 60% + metadata 40% |
| `track_match_pct` | % of local track titles fuzzy-matched against MB tracklist |
| `count_match` | Whether local file count matches MB track count |
| `acoustid_mbids` | MB release IDs returned by AcoustID (up to 5, pipe-separated) |

Single-result matches with a combined score below 35 are flagged as `review` rather than `matched` to avoid false positives.

---

## Tags written

For every file in the folder:

- Title, Artist, Album Artist
- Track number (with total e.g. 3/12)
- Disc number (with total e.g. 1/2)
- Year / Date
- Label
- Catalogue number
- Cover art (from Cover Art Archive)

---

## Folder renaming

After tagging, each folder is renamed to:
```
Artist - Title (Year)
```

For example:
```
ANJ111 Signalrunners & Julie Thompson - These Shoulders
→ Signalrunners & Julie Thompson - These Shoulders (2008)

1999 - DJ Tiesto - Sparkles [BH 118-5] WEB
→ DJ Tiesto - Sparkles (1999)

jeremy-soule-the-elder-scrolls-v-skyrim
→ Jeremy Soule - The Elder Scrolls V: Skyrim (2011)
```

---

## Flags

| Flag | Scripts | Effect |
|---|---|---|
| `--apply` | taggers, tagger_undo | Tag for real / execute undo (default is dry run) |
| `--skip-art` | taggers | Skip cover art download |
| `--auto` | lookup | Auto-pick best match when multiple results found |
| `--review` | lookup | Flag all multi-result folders for manual review |
| `--move` | lookup | Dry run: show which review/no-match folders would be moved |
| `--move --apply` | lookup | Move review folders to `To Review\` and no-match folders to `No Match\` |
| `--apply` | move_from_report | Execute moves from an existing report (default is dry run) |
| `--no-fingerprint` | mb_lookup | Skip AcoustID fingerprinting |
| `--fpcalc PATH` | mb_lookup | Path to fpcalc.exe if not in default tools folder |

---

## After tagging

Run the tagged folders through Picard afterwards to confirm. Since MBIDs are written into the file tags, Picard will recognise each release instantly rather than needing to search.

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Running without the command line

Double-click any `.bat` file to open a terminal and run the script automatically:

| File | Action |
|---|---|
| `Run - Anjuna Lookup.cmd` | Run Anjuna batch lookup |
| `Run - Anjuna Tagger (Dry Run).cmd` | Preview Anjuna tag changes |
| `Run - Anjuna Tagger (Apply).cmd` | Apply Anjuna tags |
| `Run - Tagger Undo (Dry Run).cmd` | Preview tagger undo |
| `Run - Tagger Undo (Apply).cmd` | Execute tagger undo |
| `Run - MB Lookup.cmd` | Run general-purpose lookup |
| `Run - MB Tagger (Dry Run).cmd` | Preview MB tag changes |
| `Run - MB Tagger (Apply).cmd` | Apply MB tags |
| `Run - Tiesto Lookup.cmd` | Run Tiesto collection lookup |
| `Run - Move from Report (Dry Run).cmd` | Preview folder moves from existing report |
| `Run - Move from Report (Apply).cmd` | Execute folder moves from existing report |
| `Run - Rename to CatNo (Dry Run).cmd` | Preview folder renames to CATNO format |
| `Run - Rename to CatNo (Apply).cmd` | Execute folder renames to CATNO format |
| `Run - Rename Undo (Dry Run).cmd` | Preview rename undo |
| `Run - Rename Undo (Apply).cmd` | Execute rename undo |
| `Run - Fix Featuring (Dry Run).cmd` | Preview featuring tag moves |
| `Run - Fix Featuring (Apply).cmd` | Apply featuring tag moves |
| `Run - FLAC to CUE.cmd` | Generate CUE sheets for FLAC files |

---

## Files

| File | Description |
|---|---|
| `anjuna_mb_lookup.py` | Anjuna-specific lookup |
| `anjuna_tagger.py` | Anjuna tagger |
| `mb_lookup.py` | General-purpose lookup |
| `tiesto_lookup.py` | Tiesto collection lookup |
| `mb_tagger.py` | Generic tagger |
| `tagger_undo.py` | Reverses folder renames from tagger runs |
| `rename_to_catno.py` | Renames album folders to CATNO - Album Name |
| `rename_undo.py` | Reverses renames made by rename_to_catno.py |
| `fix_featuring.py` | Moves feat. credits from Artist tag to Title tag |
| `flac_to_cue.py` | Generates CUE sheets from MusicBrainz data for FLAC splitting |
| `move_from_report.py` | Moves review/no-match folders from an existing lookup report |
| `anjuna_lookup_viewer.html` | Lookup viewer (works for all lookup CSVs) |
| `CHANGELOG.md` | Version history |
| `reports\` | Per-run CSV reports |
