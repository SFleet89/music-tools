# Clean Album Folders

Scans album folders and moves non-music files (JPG, NFO, SFV, M3U, LOG etc.) to a holding folder, leaving only the music behind. The holding folder mirrors the original structure so everything can be restored to its exact original location if needed.

Nothing is moved until you confirm. Dry run by default.

---

## What gets kept

- **Music files** — MP3, FLAC, AAC, M4A, OGG, WMA, WAV, AIFF, APE, OPUS, WavPack
- **CUE files** — only if paired with a single audio file larger than 100MB (single-file rip that needs splitting). CUE files in normal multi-track albums are moved.

## What gets moved

Everything else — JPG, PNG, NFO, SFV, MD5, M3U, LOG, TXT, and any other non-music files.

---

## Requirements

```
pip install mutagen
```

---

## Setup

Set the three path constants at the top of the script:

```python
DEFAULT_FOLDER = r"C:\Music\To Sort"
HOLDING_FOLDER = r"C:\Music\Extras"
REPORTS_FOLDER = r"C:\Music\tools\clean_album_folders\reports"
```

---

## Usage

```
python clean_album_folders.py                      # dry run, folder picker
python clean_album_folders.py --apply              # clean for real
python clean_album_folders.py --path "C:\Music"    # override folder path
python clean_album_folders.py --path "C:\Music" --apply
```

---

## Recommended workflow

```
# Step 1 — dry run to see what would be moved
python clean_album_folders.py

# Step 2 — review the report CSV

# Step 3 — clean for real
python clean_album_folders.py --apply
```

---

## Holding folder

Files are moved to the holding folder with the full original path preserved. For example:

```
Original : C:\Music\Artist\Album\cover.jpg
Holding  : C:\Music\Extras\Artist\Album\cover.jpg
```

This means restoring any file is just a matter of moving it back — the path tells you exactly where it came from.

---

## Output

Every run saves a timestamped CSV to your reports folder:

| File | Contents |
|---|---|
| `clean_album_folders_dry_TIMESTAMP.csv` | Dry run preview |
| `clean_album_folders_applied_TIMESTAMP.csv` | Results of a live run |

### CSV columns

| Column | Description |
|---|---|
| File | Relative path of the file |
| Extension | File extension |
| Action | keep or move to holding |
| Reason | Why the file was kept or moved |
| Status | kept / would move / moved / error |

---

## Supported music formats

MP3, FLAC, AAC, M4A, OGG, WMA, WAV, AIFF, APE, OPUS, WavPack

---

## Files

| File | Description |
|---|---|
| `clean_album_folders.py` | Main script |
| `Clean_Album_Folders_Run_Commands.txt` | Quick reference |
| `reports\clean_album_folders_*.csv` | Per-run reports |
