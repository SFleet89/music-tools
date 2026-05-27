# Sort By Artist

Sorts audio files from a flat folder into artist subfolders.

## What it does

Scans the **root level only** (non-recursive) of the selected folder for supported audio files (MP3, FLAC, AAC, M4A, etc.). For each file it:

1. Reads the **Artist** tag via mutagen (primary source).
2. Falls back to parsing **"Artist - Title"** from the filename if no tag is found.
3. Strips featured-artist credits (`ft.`, `feat.`, `featuring`, `with`) from the artist name.
4. Creates a subfolder named after the artist inside the source folder and moves the file into it.

Files where no artist can be determined, or whose artist is a "Various Artists" variant (`VA`, `V.A.`, etc.), are left in place.

## Usage

| Command | What happens |
|---|---|
| `python sort_by_artist.py --pick` | Opens a folder dialog — dry run, nothing moved |
| `python sort_by_artist.py --pick --apply` | Opens a folder dialog — moves files after confirmation |
| `python sort_by_artist.py --path "C:\folder"` | Uses the given folder — dry run |
| `python sort_by_artist.py --path "C:\folder" --apply` | Uses the given folder — moves files |

Or just double-click one of the `.cmd` launchers.

## Output

A timestamped CSV report is saved to `sort_by_artist/reports/` after every run (dry or applied):

| Column | Description |
|---|---|
| `file` | Original filename |
| `artist_found` | Artist name detected |
| `artist_source` | `tag`, `filename`, or `none` |
| `destination` | Full path where the file would be / was moved |
| `status` | `pending` (dry run), `moved`, `skipped`, or `error` |
| `notes` | Reason for skip, collision rename, or error message |

## Requirements

- Python 3.10+
- `mutagen` — `pip install mutagen`
