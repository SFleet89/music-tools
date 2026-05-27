# Sort CD Tracks

Reads the DISCNUMBER tag from music files and automatically moves them into CD subfolders (CD1, CD2, CD3 etc.). Works on a single album folder or recursively across an entire library.

Nothing is moved until you confirm. Dry run by default.

---

## How it works

For each folder it scans, the script reads the DISCNUMBER tag from every music file. Files are moved into CD1/, CD2/ etc. subfolders based on their disc number. This works whether an album has one disc or several — a folder containing only disc-1 files will have those files moved into CD1/, and a two-disc album gets both CD1/ and CD2/ created.

If you point the script at a parent folder that contains album subfolders (rather than music files directly), it automatically switches to recursive mode and scans all subfolders — no need to pass `--recursive` manually.

Handles both disc number formats:
- Plain number — `1`, `2`
- Fraction format — `1/2`, `2/2`

---

## Requirements

```
pip install mutagen
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
| `--recursive` | Scan all subfolders of the target rather than just the target itself. Usually not needed — the script auto-detects this when no music files are found directly in the pointed folder. |
| `--path PATH` | Override the folder path, skips the dialog. |

---

## What gets skipped

| Situation | What happens |
|---|---|
| Folder already has CD subfolders | Skipped entirely |
| No DISCNUMBER tags found in any file | Skipped with a warning |
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
