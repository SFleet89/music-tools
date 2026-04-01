# Sort CD Tracks

Reads the DISCNUMBER tag from music files and automatically moves them into CD subfolders (CD1, CD2, CD3 etc.). Works on a single album folder or recursively across an entire library.

Nothing is moved until you confirm. Dry run by default.

---

## How it works

For each folder it scans, the script reads the DISCNUMBER tag from every music file. If files with two or more different disc numbers are found, they get moved into the appropriate CD subfolder. Folders that are already sorted (already have CD subfolders) or only have a single disc are left untouched.

Handles both disc number formats:
- Plain number — `1`, `2`
- Fraction format — `1/2`, `2/2`

---

## Requirements

```
pip install mutagen
```

---

## Setup

Set the reports folder path at the top of the script:
```python
REPORTS_FOLDER = r"C:\Users\neo_s\...\tools\sort_cd_tracks\reports"
```

---

## Usage

```
python sort_cd_tracks.py                          # dry run, folder picker (single album)
python sort_cd_tracks.py --apply                  # move for real
python sort_cd_tracks.py --recursive              # scan all album subfolders, dry run
python sort_cd_tracks.py --recursive --apply      # sort all albums for real
python sort_cd_tracks.py --path "C:\Music\Album"
python sort_cd_tracks.py --path "C:\Music" --recursive --apply
```

---

## Recommended workflow

```
# Step 1 — dry run to see what would be sorted
python sort_cd_tracks.py --recursive

# Step 2 — sort for real
python sort_cd_tracks.py --recursive --apply
```

---

## Flags

| Flag | Description |
|---|---|
| `--apply` | Move for real. Without this the script is always a dry run. |
| `--recursive` | Scan all subfolders of the target rather than just the target itself. Skips folders that are already sorted or single-disc. |
| `--path PATH` | Override the folder path, skips the dialog. |

---

## What gets skipped

| Situation | What happens |
|---|---|
| Folder already has CD subfolders | Skipped entirely |
| All files have the same disc number | Skipped (single disc, nothing to sort) |
| No DISCNUMBER tags found | Skipped with a warning |
| File has no disc tag but others in the folder do | Left in place, noted in report |
| Destination file already exists | Skipped with a warning |

---

## Output

Every run saves a timestamped CSV to your reports folder:

| File | Contents |
|---|---|
| `sort_cd_tracks_dry_TIMESTAMP.csv` | Dry run preview |
| `sort_cd_tracks_applied_TIMESTAMP.csv` | Results of a live run |

### CSV columns

| Column | Description |
|---|---|
| Filename | The music file name |
| Disc Number | Disc number read from the tag |
| Destination Folder | CD subfolder it was (or would be) moved to |
| Status | moved / would move / skipped / no disc tag / error |

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Running without the command line

Double-click any `.bat` file to open a terminal and run the script automatically:

| File | Action |
|---|---|
| `Run - Sort CD Tracks (Dry Run).bat` | Preview which files would be sorted |
| `Run - Sort CD Tracks (Apply).bat` | Sort files into CD subfolders |

---

## Files

| File | Description |
|---|---|
| `sort_cd_tracks.py` | Main script |
| `Sort_CD_Tracks_Run_Commands.txt` | Quick reference |
| `reports\sort_cd_tracks_*.csv` | Per-run reports |
