"""
create_test_environment.py — v1.0 — 2026-05-20
Generates the testing_environment/ folder with reproducible test audio
files and junk files covering all Music Tools script test scenarios.

Audio files are tiny silent WAVs/MP3s/FLACs with embedded tags.
No real audio — no copyright concerns, no size issues, fully reproducible.
Re-running wipes and recreates the whole folder from scratch.

Requires:
    pip install mutagen

Usage:
    python create_test_environment.py            # asks before overwriting
    python create_test_environment.py --force    # overwrite without prompting
"""

import sys
import json
import shutil
import struct
from pathlib import Path
from datetime import date

# ── Check mutagen before anything else ────────────────────────────────────────
try:
    from mutagen.id3 import (
        ID3, ID3NoHeaderError,
        TIT2, TPE1, TPE2, TALB, TRCK, TXXX,
    )
    from mutagen.flac import FLAC
except ImportError:
    print("ERROR: mutagen is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
TEST_ENV   = SCRIPT_DIR / "testing_environment"
FORCE      = "--force" in sys.argv

TODAY = date.today().isoformat()

# ─────────────────────────────────────────────────────────────────────────────
#  Low-level audio helpers
#  All audio is silent.  Files are tiny (< 2 KB each).
# ─────────────────────────────────────────────────────────────────────────────

def _mp3_frame_bytes(bitrate_kbps: int = 128) -> bytes:
    """
    One silent MPEG1 Layer 3 stereo frame at 44100 Hz.

    Frame header breakdown:
      0xFF 0xFB  — sync (11 bits) + MPEG1 + Layer3 + not-CRC-protected
      byte2      — bitrate index + 44100Hz sample rate + no padding + no private
      0x04       — stereo mode + not copyrighted + original + no emphasis

    Frame sizes:
      128 kbps → 144 * 128000 / 44100 = 417 bytes
      320 kbps → 144 * 320000 / 44100 = 1044 bytes
    """
    if bitrate_kbps == 320:
        byte2, size = 0xE0, 1044
    else:  # 128 kbps
        byte2, size = 0x90, 417
    return bytes([0xFF, 0xFB, byte2, 0x04]) + bytes(size - 4)


def _write_mp3(path: Path, bitrate_kbps: int = 128, num_frames: int = 1) -> None:
    """Write a bare MP3 file (N silent frames, no ID3 header yet)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = _mp3_frame_bytes(bitrate_kbps)
    path.write_bytes(frame * num_frames)


def _write_flac(path: Path) -> None:
    """
    Write a minimal valid FLAC file (STREAMINFO only, no audio frames, no tags).

    STREAMINFO field layout (34 bytes):
      min/max blocksize  — 2+2 bytes  (4096 each)
      min/max framesize  — 3+3 bytes  (0 = unknown)
      8-byte packed field:
        bits 63-44  sample_rate    = 44100 (0xAC44)
        bits 43-41  channels - 1  = 0      (mono)
        bits 40-36  bps - 1       = 15     (16-bit)
        bits 35-0   total_samples = 0
      MD5 signature      — 16 bytes  (all zero = unset)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data  = b'fLaC'
    data += bytes([0x80, 0x00, 0x00, 0x22])          # last-block | STREAMINFO | length 34
    data += struct.pack('>HH', 4096, 4096)            # min/max blocksize
    data += b'\x00\x00\x00\x00\x00\x00'              # min/max framesize
    data += struct.pack('>Q',                         # sample_rate + channels + bps + samples
        (44100 << 44) | (0 << 41) | (15 << 36) | 0)
    data += b'\x00' * 16                              # MD5
    path.write_bytes(data)


def _tag_mp3(path: Path, **tags) -> None:
    """Write ID3v2.3 tags to an existing MP3 file."""
    try:
        id3 = ID3(str(path))
    except ID3NoHeaderError:
        id3 = ID3()
    mapping = {
        'title':        ('TIT2', lambda v: TIT2(encoding=3, text=v)),
        'artist':       ('TPE1', lambda v: TPE1(encoding=3, text=v)),
        'album':        ('TALB', lambda v: TALB(encoding=3, text=v)),
        'tracknumber':  ('TRCK', lambda v: TRCK(encoding=3, text=str(v))),
        'album_artist': ('TPE2', lambda v: TPE2(encoding=3, text=v)),
    }
    for key, val in tags.items():
        if val is None:
            continue
        if key in mapping:
            frame_id, builder = mapping[key]
            id3[frame_id] = builder(val)
        elif key == 'catalognumber':
            id3.add(TXXX(encoding=3, desc='CATALOGNUMBER', text=str(val)))
        elif key == 'mb_album_id':
            id3.add(TXXX(encoding=3, desc='MusicBrainz Album Id', text=str(val)))
    id3.save(str(path), v2_version=3)


def _tag_flac(path: Path, **tags) -> None:
    """Write VorbisComment tags to an existing FLAC file."""
    f = FLAC(str(path))
    key_map = {
        'title':        'title',
        'artist':       'artist',
        'album':        'album',
        'tracknumber':  'tracknumber',
        'album_artist': 'albumartist',
        'catalognumber':'catalognumber',
        'mb_album_id':  'musicbrainz_albumid',
    }
    for key, val in tags.items():
        if val is not None:
            f[key_map.get(key, key)] = [str(val)]
    f.save()


# ── High-level helpers used by test builders ──────────────────────────────────

def make_mp3(path: Path, bitrate_kbps: int = 128, num_frames: int = 1, **tags) -> None:
    _write_mp3(path, bitrate_kbps, num_frames)
    if tags:
        _tag_mp3(path, **tags)
    print(f"  [mp3 {bitrate_kbps:3}k] {path.relative_to(SCRIPT_DIR)}")


def make_flac(path: Path, **tags) -> None:
    _write_flac(path)
    if tags:
        _tag_flac(path, **tags)
    print(f"  [flac    ] {path.relative_to(SCRIPT_DIR)}")


def make_stub(path: Path, content: bytes = b'') -> None:
    """Create an empty (or near-empty) non-audio file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f"  [stub    ] {path.relative_to(SCRIPT_DIR)}")


def make_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    print(f"  [dir     ] {path.relative_to(SCRIPT_DIR)}")


# ─────────────────────────────────────────────────────────────────────────────
#  Test case builders — one per script group
# ─────────────────────────────────────────────────────────────────────────────

def build_duplicate_finder():
    """
    TC-DF-01  Exact match   — same tags, same bitrate → auto-move to Duplicates
    TC-DF-02  Near match    — tags differ slightly (&/and, accent) → fuzzy match
    TC-DF-03  Better quality— same tags, unsorted is 320 kbps → Better Quality folder
    TC-DF-04  No match      — not in library at all → left untouched
    TC-DF-05  Fingerprint   — different tags, identical audio bytes → FP match only
    """
    print("\n[Duplicate Finder]")
    base = TEST_ENV / "duplicate_finder"
    lib  = base / "library"
    uns  = base / "unsorted"

    # ── Library (reference) ───────────────────────────────────────────────────
    make_mp3(lib / "Artist A - Perfect Day.mp3",
             title="Perfect Day", artist="Artist A",
             album="The Album", tracknumber="1")
    make_mp3(lib / "Artist B - Another Song.mp3",
             title="Another Song", artist="Artist B",
             album="B Album", tracknumber="1")

    # ── TC-DF-01: Exact match ─────────────────────────────────────────────────
    # Same tags, same bitrate (128 k), same silent audio bytes.
    # Expected: detected as EXACT or DUPLICATE → moved to Duplicates folder.
    make_mp3(uns / "TC-DF-01 Exact Match.mp3",
             title="Perfect Day", artist="Artist A",
             album="The Album", tracknumber="1")

    # ── TC-DF-02: Near match (fuzzy) ──────────────────────────────────────────
    # Same track but artist tag uses "&" instead of "A".
    # Expected WITH fuzzy enabled:  detected as DUPLICATE (fuzzy score ≥ threshold)
    # Expected WITHOUT fuzzy:       NO MATCH (strict comparison fails)
    make_mp3(uns / "TC-DF-02 Near Match Fuzzy.mp3",
             title="Perfect Day", artist="Artist & A",
             album="The Album", tracknumber="1")

    # ── TC-DF-03: Better quality ──────────────────────────────────────────────
    # Same tags as library "Perfect Day" but encoded at 320 kbps.
    # Expected: detected as BETTER (higher bitrate) → moved to Better Quality folder.
    make_mp3(uns / "TC-DF-03 Better Quality.mp3",
             bitrate_kbps=320,
             title="Perfect Day", artist="Artist A",
             album="The Album", tracknumber="1")

    # ── TC-DF-04: No match ────────────────────────────────────────────────────
    # Completely different tags — not in the library at all.
    # Expected: NO MATCH → file left in unsorted folder, untouched.
    make_mp3(uns / "TC-DF-04 No Match.mp3",
             title="Ghost Track", artist="Unknown DJ",
             album="No Library Album", tracknumber="1")

    # ── TC-DF-05: Fingerprint match ───────────────────────────────────────────
    # Tags are completely different from any library file, but the audio bytes
    # are identical to the library "Perfect Day" (both are silent 128 k frames).
    # Expected: tag/name pass → NO MATCH; fingerprint pass → DUPLICATE.
    #
    # NOTE: The fingerprint pass requires fpcalc (Chromaprint) to be installed
    # and on PATH.  For fpcalc to generate a reliable fingerprint the audio
    # should ideally be > 3.5 seconds.  These minimal single-frame files
    # (~26 ms) may yield an unreliable fingerprint — increase num_frames to
    # ~192 for a proper 5-second sample if you need a live fingerprint test.
    _write_mp3(uns / "TC-DF-05 Fingerprint Only.mp3")   # same bytes as library copy
    _tag_mp3(uns / "TC-DF-05 Fingerprint Only.mp3",
             title="Mix Track 01", artist="DJ Unknown",
             album="Test Mix 2024", tracknumber="1")
    print(f"  [mp3 128k] "
          f"{(uns / 'TC-DF-05 Fingerprint Only.mp3').relative_to(SCRIPT_DIR)}")

    # Output buckets created by the script at runtime (not pre-created):
    #   base/duplicates/
    #   base/better_quality/
    print("  (duplicates/ and better_quality/ created at runtime by the script)")


def build_filename_scanner():
    """
    TC-FS-00  Clean control   — no issues, should NOT be flagged
    TC-FS-01  Double spaces   — two consecutive spaces in filename
    TC-FS-02  Underscores     — underscores used instead of spaces
    TC-FS-03  Scene brackets  — [WEB-RIP] style scene tags in filename
    TC-FS-04  All caps        — fully uppercase filename
    """
    print("\n[Filename Scanner]")
    base = TEST_ENV / "filename_scanner"

    # TC-FS-00: Clean — should not be flagged
    make_mp3(base / "Artist A - Clean File.mp3",
             title="Clean File", artist="Artist A", album="Test Album")

    # TC-FS-01: Double spaces — should flag as double_spaces
    make_mp3(base / "Artist  A - Double  Space Track.mp3",
             title="Double Space Track", artist="Artist A", album="Test Album")

    # TC-FS-02: Underscores — should flag as underscores
    make_mp3(base / "Artist_A - Underscores_In_Name.mp3",
             title="Underscores In Name", artist="Artist A", album="Test Album")

    # TC-FS-03: Scene brackets — should flag as brackets/scene tags
    make_mp3(base / "Artist A - [WEB-RIP] Cool Track (2024).mp3",
             title="Cool Track", artist="Artist A", album="Test Album")

    # TC-FS-04: All caps — should flag as casing issue
    make_mp3(base / "ARTIST A - ALL CAPS TRACK.mp3",
             title="All Caps Track", artist="Artist A", album="Test Album")


def build_clean_album_folders():
    """
    TC-CAF-01  NFO file        — info.nfo should be flagged/removed
    TC-CAF-02  Non-cover JPG   — booklet scans (multi-digit suffix) should be removed
    TC-CAF-03  TXT file        — liner_notes.txt should be flagged/removed
    TC-CAF-04  Scene folder    — "[WEB FLAC]" in folder name should be stripped
    """
    print("\n[Clean Album Folders]")
    base  = TEST_ENV / "clean_album_folders"
    album = base / "The Best Album [WEB FLAC]"   # TC-CAF-04: scene tag in folder name

    # Good audio file — should NOT be touched
    make_mp3(album / "Artist A - Track 01.mp3",
             title="Track 01", artist="Artist A",
             album="The Best Album", tracknumber="1")

    # Junk files the script should flag or remove
    make_stub(album / "info.nfo")               # TC-CAF-01
    make_stub(album / "booklet_scan_01.jpg")    # TC-CAF-02 (multi-digit = not cover)
    make_stub(album / "liner_notes.txt")        # TC-CAF-03


def build_rename_scripts():
    """
    TC-RN-01  Ready to rename  — all required tags present (artist, album, catno)
    TC-RN-02  Missing tags     — no tags at all, edge-case handling
    TC-RN-03  Feat. in artist  — "Artist feat. Someone" in artist tag
    """
    print("\n[Rename Scripts]")
    base = TEST_ENV / "rename_scripts"

    # TC-RN-01: Fully tagged — rename_album_folders / rename_to_catno should succeed
    make_mp3(base / "ready_to_rename" / "Artist A - Perfect Day.mp3",
             title="Perfect Day", artist="Artist A",
             album="The Album", tracknumber="1",
             album_artist="Artist A", catalognumber="TEST001")

    # TC-RN-02: No tags — scripts should handle gracefully (skip or report as error)
    make_mp3(base / "missing_tags" / "no_tags.mp3")

    # TC-RN-03: Feat. in artist tag — fix_featuring should move to title
    make_mp3(base / "feat_in_artist" / "Artist A feat. Someone - A Track.mp3",
             title="A Track", artist="Artist A feat. Someone",
             album="Collab Album", tracknumber="1")


def build_flac_to_cue():
    """
    TC-FC-01  MBID tag     — MUSICBRAINZ_ALBUMID set → direct MB lookup
    TC-FC-02  CATNO only   — CATALOGNUMBER set, no MBID → fallback search
    TC-FC-03  Untagged     — no tags at all → filename-only fallback

    IMPORTANT — TC-FC-01 MB UUID:
      The placeholder UUID below will cause a 404 from the MB API.
      Replace it with a real MusicBrainz release UUID to test the live
      lookup path.  To find one: search musicbrainz.org for a release,
      open the release page, and copy the UUID from the URL:
          /release/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
      Anjunabeats releases are a good choice (e.g. search "ANJCD008").
    """
    print("\n[FLAC to CUE]")
    base = TEST_ENV / "flac_to_cue"

    # TC-FC-01: MBID present — should query MB directly by release ID
    make_flac(base / "with_mbid" / "01 - Perfect Day.flac",
              title="Perfect Day", artist="Artist A",
              album="The Album", tracknumber="1",
              mb_album_id="REPLACE-WITH-REAL-MB-UUID-SEE-README")

    # TC-FC-02: CATALOGNUMBER only, no MBID — tests the catno search fallback
    #   ANJCD008 is a real Anjunabeats catalogue number; the script will search
    #   MB for it and (if online) return the matching release.
    make_flac(base / "with_catno" / "01 - Another Track.flac",
              title="Another Track", artist="Artist B",
              album="The B Album", tracknumber="1",
              catalognumber="ANJCD008")

    # TC-FC-03: No tags — filename used as fallback for title
    make_flac(base / "untagged" / "01 - Unknown Track.flac")


def build_setup_wizard():
    """
    TC-SW-01  Blank config dir  — wizard creates fresh music_config.json
    TC-SW-02  Existing config   — wizard loads + displays existing values
    TC-SW-03  --reset flag      — documented only (no files needed)
    """
    print("\n[Setup Wizard]")
    base = TEST_ENV / "setup_wizard"

    # TC-SW-01: Empty directory — wizard should write a brand-new config here
    make_dir(base / "blank_config")

    # TC-SW-02: Pre-populated config — wizard should load and display these values
    existing = base / "existing_config"
    make_dir(existing)
    test_config = {
        "library_folder":          str(TEST_ENV / "duplicate_finder" / "library"),
        "unsorted_folder":         str(TEST_ENV / "duplicate_finder" / "unsorted"),
        "duplicates_folder":       str(TEST_ENV / "duplicate_finder" / "duplicates"),
        "better_quality_folder":   str(TEST_ENV / "duplicate_finder" / "better_quality"),
        "fuzzy_match":             True,
        "fuzzy_threshold":         88,
        "duration_tolerance":      3,
        "file_size_tolerance":     1,
        "threads":                 0,
        "use_acoustid":            False,
        "acoustid_api_key":        "",
        "fp_similarity_threshold": 90,
    }
    config_path = existing / "music_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=2)
    print(f"  [json    ] {config_path.relative_to(SCRIPT_DIR)}")
    print("  (TC-SW-03 --reset: no files needed — run setup_music_tools.py --reset directly)")


# ─────────────────────────────────────────────────────────────────────────────
#  README content (written into testing_environment/README.md by the script)
# ─────────────────────────────────────────────────────────────────────────────

README_CONTENT = f"""\
# Music Tools — Testing Environment

Generated by `create_test_environment.py` on {TODAY}.
Re-run that script to wipe and recreate everything from scratch.

All audio files are tiny silent MP3s or FLACs with embedded tags.
They exist purely to trigger specific code paths in each script.
No real audio, no copyright concerns.

---

## How to use

Each test case below lists:
- **Files** — what was created and why
- **Setup** — how to point the script at the test folder
- **Expected outcome** — what the script should do or report
- **Pass / Fail** — how to tell if it worked

The scripts are in `--dry-run` mode by default, so nothing moves or changes
until you add `--apply`.  For these tests, dry-run output is usually enough
to confirm correct behaviour.

---

## Duplicate Finder (`find_music_duplicates.py`)

Test data lives in `testing_environment/duplicate_finder/`.

**How to configure for testing:**
Point `music_config.json` at these folders before running:
- `library_folder`  → `…/testing_environment/duplicate_finder/library`
- `unsorted_folder` → `…/testing_environment/duplicate_finder/unsorted`
- `duplicates_folder`     → `…/testing_environment/duplicate_finder/duplicates`
- `better_quality_folder` → `…/testing_environment/duplicate_finder/better_quality`

The setup wizard test config at `setup_wizard/existing_config/music_config.json`
is already set up with these paths — copy it into `duplicate_finder/` to use it.

---

### TC-DF-01 — Exact Match

**File:** `unsorted/TC-DF-01 Exact Match.mp3`
**Tags:** Artist A / Perfect Day / The Album / track 1 / 128 kbps
**Matches:** `library/Artist A - Perfect Day.mp3` (identical tags + bitrate)

**Expected outcome:** Script detects EXACT or DUPLICATE match.
In dry-run: CSV shows status `exact` or `duplicate` for this file.
In apply mode: file is moved to the `duplicates` folder.

**Pass:** File appears in the CSV with a match against "Artist A - Perfect Day".
**Fail:** File reported as NO MATCH.

---

### TC-DF-02 — Near Match (Fuzzy)

**File:** `unsorted/TC-DF-02 Near Match Fuzzy.mp3`
**Tags:** Artist: "Artist & A" / Title: "Perfect Day" / Album: "The Album"
**Difference from library:** artist tag uses "&" instead of "A"

**Expected outcome WITH fuzzy matching enabled:**
  Score ≥ threshold → detected as DUPLICATE.

**Expected outcome WITHOUT fuzzy (strict mode):**
  Exact string comparison fails → NO MATCH.

**How to test both:** Run once with `"fuzzy_match": true` in config, once with `false`.

**Pass (fuzzy on):** CSV shows match against "Artist A - Perfect Day".
**Pass (fuzzy off):** CSV shows NO MATCH for this file.

---

### TC-DF-03 — Better Quality

**File:** `unsorted/TC-DF-03 Better Quality.mp3`
**Tags:** Artist A / Perfect Day / The Album — same as library
**Bitrate:** 320 kbps (library copy is 128 kbps)

**Expected outcome:** Script detects the same track but the unsorted copy has
a higher bitrate → status BETTER → moved to `better_quality` folder.

**Pass:** CSV shows status `better` and the file is moved (in apply mode).
**Fail:** Reported as EXACT/DUPLICATE instead of BETTER, or as NO MATCH.

---

### TC-DF-04 — No Match

**File:** `unsorted/TC-DF-04 No Match.mp3`
**Tags:** DJ Unknown / Ghost Track / No Library Album
**Library match:** None — this track does not exist in the library.

**Expected outcome:** Both tag/name pass and fingerprint pass (if enabled) return
NO MATCH.  File is left in place, untouched.

**Pass:** CSV shows NO MATCH; file remains in the unsorted folder.
**Fail:** File incorrectly matched to a library track.

---

### TC-DF-05 — Fingerprint Match Only

**File:** `unsorted/TC-DF-05 Fingerprint Only.mp3`
**Tags:** DJ Unknown / Mix Track 01 / Test Mix 2024 (completely different from library)
**Audio content:** Identical bytes to `library/Artist A - Perfect Day.mp3`
(both are silent 128 kbps frames — same fingerprint when processed by fpcalc)

**Expected outcome:**
  Tag/name pass: NO MATCH (tags are different).
  Fingerprint pass: DUPLICATE (audio fingerprint matches library copy).

**Requirements:** fpcalc (Chromaprint) must be installed and on PATH.

⚠️  **Known limitation with test files:** These minimal files are ~26 ms long
(one MPEG frame). Chromaprint typically needs ≥ 3.5 seconds of audio to
generate a reliable fingerprint. If fpcalc returns an empty or error result,
regenerate TC-DF-05 with `num_frames=192` in the script (≈ 5 seconds, ~80 KB).

**Pass:** CSV shows NO MATCH on tag pass, then DUPLICATE on fingerprint pass.
**Fail:** Fingerprint pass also returns NO MATCH, or match is against wrong file.

---

## Filename Scanner (`scan_music_filenames.py`)

Test data lives in `testing_environment/filename_scanner/`.

Run the scanner pointed at this folder:
```
python scan_music_filenames.py --path "…\\testing_environment\\filename_scanner"
```

---

### TC-FS-00 — Clean Control

**File:** `Artist A - Clean File.mp3`
**Expected outcome:** NOT flagged. Appears only in the "all files" count, not in
any issue CSV.

**Pass:** No issue reported for this file.
**Fail:** Flagged for any issue.

---

### TC-FS-01 — Double Spaces

**File:** `Artist  A - Double  Space Track.mp3` (two spaces before "A", two before "Space")
**Expected outcome:** Flagged in `scan_03_double_spaces_*.csv`.

**Pass:** File appears in the double-spaces CSV.
**Fail:** File not flagged, or flagged under a different issue category.

---

### TC-FS-02 — Underscores

**File:** `Artist_A - Underscores_In_Name.mp3`
**Expected outcome:** Flagged in `scan_01_underscores_*.csv`.

**Pass:** File appears in the underscores CSV.

---

### TC-FS-03 — Scene Brackets

**File:** `Artist A - [WEB-RIP] Cool Track (2024).mp3`
**Expected outcome:** Flagged for brackets or scene tags.

**Pass:** File flagged; appears in a brackets/scene-tags CSV.

---

### TC-FS-04 — All Caps

**File:** `ARTIST A - ALL CAPS TRACK.mp3`
**Expected outcome:** Flagged for casing issue.

**Pass:** File flagged; appears in a casing CSV.

---

## Clean Album Folders (`clean_album_folders.py`)

Test data lives in `testing_environment/clean_album_folders/`.

Run the script pointed at this folder:
```
python clean_album_folders.py --path "…\\testing_environment\\clean_album_folders"
```

---

### TC-CAF-01 — NFO File

**File:** `The Best Album [WEB FLAC]/info.nfo`
**Expected outcome:** Flagged for deletion. Not an audio file; typically left by
scene release groups.

---

### TC-CAF-02 — Non-Cover JPG

**File:** `The Best Album [WEB FLAC]/booklet_scan_01.jpg`
**Expected outcome:** Flagged. Multi-digit suffix (`_01`) indicates it's a booklet
scan, not a cover image.

---

### TC-CAF-03 — TXT File

**File:** `The Best Album [WEB FLAC]/liner_notes.txt`
**Expected outcome:** Flagged for deletion. Plain-text files are junk in an album folder.

---

### TC-CAF-04 — Scene Tag in Folder Name

**Folder:** `The Best Album [WEB FLAC]/`
**Expected outcome:** Script suggests renaming to strip the `[WEB FLAC]` scene tag,
leaving `The Best Album`.

**Pass:** Folder rename proposed in dry-run output or CSV.
**Fail:** Folder name not flagged.

---

## Rename Scripts

Test data lives in `testing_environment/rename_scripts/`.

---

### TC-RN-01 — Ready to Rename

**File:** `ready_to_rename/Artist A - Perfect Day.mp3`
**Tags:** Full set — artist, album, tracknumber, album_artist, CATALOGNUMBER=TEST001

**Scripts to test:** `rename_album_folders.py`, `rename_to_catno.py`

**Expected outcome:** Both scripts find all required tags and propose a rename.
rename_album_folders → folder renamed to standard format.
rename_to_catno      → folder renamed to "TEST001 - The Album" (or similar).

**Pass:** Rename proposed in dry-run CSV.
**Fail:** Script skips the file or reports missing tags.

---

### TC-RN-02 — Missing Tags

**File:** `missing_tags/no_tags.mp3`
**Tags:** None

**Expected outcome:** Scripts detect missing required tags and skip or report the
file as an error, without crashing.

**Pass:** File reported in the CSV with status `skipped` or `error`; no crash.
**Fail:** Script crashes with an unhandled exception.

---

### TC-RN-03 — Feat. in Artist Tag

**File:** `feat_in_artist/Artist A feat. Someone - A Track.mp3`
**Tags:** artist = "Artist A feat. Someone"

**Script to test:** `fix_featuring.py`

**Expected outcome:** Script moves the feat. credit from the artist tag to the
title tag.  After applying: artist = "Artist A", title = "A Track (feat. Someone)".

**Pass:** CSV shows the planned artist/title change. Applied correctly in apply mode.
**Fail:** Feat. credit not detected or not moved.

---

## FLAC to CUE (`flac_to_cue.py`)

Test data lives in `testing_environment/flac_to_cue/`.

Note: CUE generation queries the MusicBrainz API — an internet connection is
required for TC-FC-01 and TC-FC-02.

---

### TC-FC-01 — File with MusicBrainz Album ID

**File:** `with_mbid/01 - Perfect Day.flac`
**Tag:** `musicbrainz_albumid = REPLACE-WITH-REAL-MB-UUID-SEE-README`

⚠️  **Action required:** Replace the placeholder UUID before testing.
To find a real MB release UUID:
  1. Go to musicbrainz.org
  2. Search for an Anjunabeats release (e.g. "ANJCD008 Anjunabeats")
  3. Open the release page
  4. Copy the UUID from the URL: `/release/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
  5. Edit the FLAC tag with mutagen or a tag editor (e.g. Mp3tag)

**Expected outcome:** Script reads the MBID tag and queries MB directly.
CUE sheet generated with correct track listing from MB.

**Pass:** CUE file created; track titles match the MB release.
**Fail:** Script reports "MBID not found" or returns a blank CUE.

---

### TC-FC-02 — CATALOGNUMBER Only (No MBID)

**File:** `with_catno/01 - Another Track.flac`
**Tags:** CATALOGNUMBER = ANJCD008 (real Anjunabeats cat number; no MBID tag)

**Expected outcome:** Script finds no MBID, falls back to searching MB by
catalogue number. Returns the matching release (if online).

**Pass:** MB search returns a result; CUE sheet generated.
**Fail:** Script errors out, or falls through to filename fallback instead of
attempting the catalogue number search.

---

### TC-FC-03 — Untagged File (Filename Fallback)

**File:** `untagged/01 - Unknown Track.flac`
**Tags:** None

**Expected outcome:** Script reads no usable tags, falls back to the filename
("01 - Unknown Track") as the track title. CUE sheet generated with the
filename as the track name; a note in the log explains the fallback was used.

**Pass:** CUE file created using filename; no crash.
**Fail:** Script crashes on empty tags.

---

## Setup Wizard (`setup_music_tools.py`)

No audio files needed — the wizard works with `music_config.json` only.

---

### TC-SW-01 — Blank Config (First Run)

**Folder:** `setup_wizard/blank_config/` (empty directory)

**How to test:**
```
python setup_music_tools.py
```
When prompted for the config location, navigate to this folder.

**Expected outcome:** Wizard presents all settings with defaults.
After completing, `music_config.json` is written to the selected location
with all fields filled in.

**Pass:** Config file created; all required keys present; values match what
you entered.
**Fail:** Config not created, or missing keys.

---

### TC-SW-02 — Existing Config (Re-run)

**Folder:** `setup_wizard/existing_config/`
**File:** `music_config.json` (pre-populated with test values — paths point at
the duplicate_finder test data)

**How to test:**
```
python setup_music_tools.py
```
Navigate to `existing_config/` when prompted.

**Expected outcome:** Wizard loads the existing config and displays current
values at each prompt. Pressing Enter without typing keeps the existing value.
No fields are overwritten unless explicitly changed.

**Pass:** After running and accepting all defaults, config values are unchanged.
**Fail:** Existing values reset to defaults, or prompts show blank instead of
current value.

---

### TC-SW-03 — Reset Flag

**No files needed.**

```
python setup_music_tools.py --reset
```

**Expected outcome:** Wizard ignores any existing config and starts from
built-in defaults for all settings.

**Pass:** All prompts show factory-default values regardless of what was in the
existing config.
**Fail:** Some existing values bleed through.

---

## Re-generating the test environment

To wipe and rebuild everything from scratch:

```
python create_test_environment.py --force
```

This deletes `testing_environment/` and recreates it completely.
Safe to run at any time — it only touches the `testing_environment/` folder.
"""


def build_readme():
    print("\n[README]")
    readme_path = TEST_ENV / "README.md"
    readme_path.write_text(README_CONTENT, encoding="utf-8")
    print(f"  [md      ] {readme_path.relative_to(SCRIPT_DIR)}")


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("Music Tools — Test Environment Generator  v1.0")
    print("=" * 50)
    print(f"Target: {TEST_ENV}")

    # ── Overwrite check ───────────────────────────────────────────────────────
    if TEST_ENV.exists() and not FORCE:
        print(f"\nWARNING: {TEST_ENV.name}/ already exists.")
        print("  All existing contents will be deleted and recreated.")
        confirm = input("  Continue? (y/n): ").strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted. Nothing changed.")
            sys.exit(0)

    # ── Wipe and recreate ─────────────────────────────────────────────────────
    if TEST_ENV.exists():
        shutil.rmtree(TEST_ENV)
        print("\nDeleted existing testing_environment/")
    TEST_ENV.mkdir()

    # ── Build all test cases ──────────────────────────────────────────────────
    build_duplicate_finder()
    build_filename_scanner()
    build_clean_album_folders()
    build_rename_scripts()
    build_flac_to_cue()
    build_setup_wizard()
    build_readme()

    # ── Summary ───────────────────────────────────────────────────────────────
    file_count = sum(1 for p in TEST_ENV.rglob("*") if p.is_file())
    dir_count  = sum(1 for p in TEST_ENV.rglob("*") if p.is_dir())
    print(f"\nDone.  {file_count} files, {dir_count} folders created.")
    print(f"  Location : {TEST_ENV}")
    print(f"  README   : {TEST_ENV / 'README.md'}")
    print("\nSee README.md for test cases and expected outcomes.")


if __name__ == "__main__":
    main()
