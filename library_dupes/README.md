# Library Duplicate Finder

Scans your organized music library and finds songs that exist under more than one top-level artist folder — for example, the same track in both a dedicated artist folder and a compilation or genre folder.

Nothing is moved or deleted by the scanner. A companion script handles removals safely, moving files to a holding folder rather than deleting them outright.

---

## What it finds

| Example | Flagged? |
|---|---|
| `Massive Attack\Mezzanine\Teardrop.mp3` and `Trip Hop\Teardrop.mp3` | ✓ Yes — different top-level folders |
| `Daft Punk\Random Access Memories\Get Lucky.mp3` and `Various Artists\Get Lucky.mp3` | ✓ Yes — different top-level folders |
| `Massive Attack\Mezzanine\Teardrop.mp3` and `Massive Attack\Best Of\Teardrop.mp3` | ✗ No — same artist folder |

---

## How it works

Three matching methods are used in order:

1. **Audio fingerprint** *(requires fpcalc)* — compares actual audio content using Chromaprint. Catches renamed and retagged duplicates.
2. **Metadata tags** — matches on embedded artist and title tags. Both must be non-empty and match.
3. **Exact filename** — same filename after stripping the leading track number, excluding generic names like Intro, Outro, Main Title.

---

## Requirements

```
pip install mutagen tqdm rapidfuzz
```

**Optional — for fingerprint matching:**

Download `fpcalc` from [acoustid.org/chromaprint](https://acoustid.org/chromaprint) and set the path in `library_dupes_config.json`.

---

## Setup

1. Install dependencies:
   ```
   pip install mutagen tqdm rapidfuzz
   ```

2. Copy the example config and set your folder paths:
   ```
   cp library_dupes_config.example.json library_dupes_config.json
   ```
   Edit `library_dupes_config.json`:
   ```json
   "folders": {
     "organized": "C:\\Music\\Organized",
     "reports":   "C:\\Music\\tools\\library_dupes\\reports",
     "holding":   "C:\\Music\\tools\\library_dupes\\removed"
   }
   ```

3. Run:
   ```
   python find_library_dupes.py --no-fp
   ```

---

## Recommended workflow

```
# Step 1 — fast baseline (no fingerprinting)
python find_library_dupes.py --no-fp

# Step 2 — open library_dupes_viewer.html, review matches,
#           mark Keep / Remove decisions, download decisions CSV

# Step 3 — preview removals
python remove_library_dupes.py "library_dupes_decisions.csv" --dry-run

# Step 4 — remove for real (files go to holding folder, not deleted)
python remove_library_dupes.py "library_dupes_decisions.csv"

# Step 5 — full scan with fingerprinting to catch renamed/retagged duplicates
python find_library_dupes.py
```

---

## Usage

```
python find_library_dupes.py                      # full scan (fingerprint + metadata + filename)
python find_library_dupes.py --no-fp              # metadata + filename only (no fpcalc needed)
python find_library_dupes.py --no-filename        # fingerprint only
python find_library_dupes.py --rebuild-cache      # clear fingerprint cache and regenerate
python find_library_dupes.py --path "C:\Music"    # override organized folder
```

```
python remove_library_dupes.py "decisions.csv" --list     # preview what would be removed
python remove_library_dupes.py "decisions.csv" --dry-run  # dry run
python remove_library_dupes.py "decisions.csv"            # remove for real
python remove_library_dupes.py "decisions.csv" --undo     # restore moved files
```

---

## Sharing the fingerprint cache

If you point `fingerprint.fp_cache_file` at the same file used by the duplicate finder tools, all tools share one cache. Files only need to be fingerprinted once.

---

## Files

| File | Description |
|---|---|
| `find_library_dupes.py` | Main scanner — read-only |
| `remove_library_dupes.py` | Moves flagged duplicates to holding folder |
| `library_dupes_config.json` | Your configuration *(not committed — see example)* |
| `library_dupes_config.example.json` | Example configuration with placeholder paths |
| `library_dupes_viewer.html` | Browser-based report viewer with decision panel |
| `Library_Dupes_Run_Commands.txt` | Quick reference for scanner |
| `Library_Dupes_Remove_Commands.txt` | Quick reference for remove/undo |
