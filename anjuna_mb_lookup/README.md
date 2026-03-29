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
```

### Any other collection

```
# 1. Look up releases (fingerprint + catno + metadata fallbacks)
python mb_lookup.py

# 2. Open CSV in anjuna_lookup_viewer.html, review, export with selections

# 3. Dry run
python mb_tagger.py

# 4. Tag for real
python mb_tagger.py --apply
```

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
| `--apply` | taggers | Tag for real (default is dry run) |
| `--skip-art` | taggers | Skip cover art download |
| `--auto` | lookup | Auto-pick best match when multiple results found |
| `--review` | lookup | Flag all multi-result folders for manual review |
| `--no-fingerprint` | mb_lookup | Skip AcoustID fingerprinting |
| `--fpcalc PATH` | mb_lookup | Path to fpcalc.exe if not in default tools folder |

---

## After tagging

Run the tagged folders through Picard afterwards to confirm. Since MBIDs are written into the file tags, Picard will recognise each release instantly rather than needing to search.

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Files

| File | Description |
|---|---|
| `anjuna_mb_lookup.py` | Anjuna-specific lookup |
| `anjuna_tagger.py` | Anjuna tagger |
| `mb_lookup.py` | General-purpose lookup |
| `tiesto_lookup.py` | Tiesto collection lookup (mb_lookup v1.0) |
| `mb_tagger.py` | Generic tagger |
| `anjuna_lookup_viewer.html` | Lookup viewer (works for all lookup CSVs) |
| `CHANGELOG.md` | Version history |
| `reports\` | Per-run CSV reports |
