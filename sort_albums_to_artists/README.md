# Sort Albums Into Artist Folders

Scans a folder of album subfolders, reads the Album Artist tag (falling back to Artist if empty) from the music files inside each album, then moves each album folder into a new or existing artist subfolder.

Nothing is moved until you confirm. Dry run by default.

---

## Before and after

```
Before:
  Unsorted/
    Mezzanine/
    Pablo Honey/
    OK Computer/
    Blue Lines/

After:
  Unsorted/
    Massive Attack/
      Mezzanine/
      Blue Lines/
    Radiohead/
      Pablo Honey/
      OK Computer/
```

---

## Requirements

```
pip install mutagen
```

`tkinter` is required for the `--pick` dialog and is built into most Python installations.

---

## Usage

```
python sort_albums_to_artists.py                        # opens folder picker (default)
python sort_albums_to_artists.py --apply                # move for real
python sort_albums_to_artists.py --pick                 # pick folder with dialog
python sort_albums_to_artists.py --pick --apply         # pick and move
python sort_albums_to_artists.py --path "C:\Music"      # specify folder directly
python sort_albums_to_artists.py --path "C:\Music" --apply
```

Running with no arguments always opens the folder picker — there is no hardcoded default that runs silently.

---

## Flags

| Flag | Description |
|---|---|
| `--apply` | Move for real. Without this the script is always a dry run. |
| `--pick` | Open a native folder-picker dialog. |
| `--path PATH` | Specify the folder to scan directly on the command line. |

---

## Recommended workflow

```
# Step 1 — dry run to see what would be moved and into which artist folders
python sort_albums_to_artists.py --pick

# Step 2 — move for real
python sort_albums_to_artists.py --pick --apply
```

---

## How artist names are determined

For each album subfolder the script reads the Album Artist tag from all music files inside it (recursively, so CD1/CD2 subfolders are handled correctly). It then handles three cases:

- **All files agree** — artist name used automatically
- **Files disagree** — prompts you to choose from the conflicting values, with file counts shown for each option. You can also type a custom name or skip the album.
- **No artist tag found** — prompts you to type a name or skip

---

## Conflict resolution

```
  CONFLICT in: Mezzanine
  Path       : C:\Music\Unsorted\Mezzanine
  Multiple Album Artist tags found:

    [1] Massive Attack  (11 file(s))
          01 - Angel.flac
          02 - Risingson.flac
          03 - Teardrop.flac
          ... and 8 more

    [2] Various Artists  (1 file(s))
          00 - Bonus.flac

    [s] Skip this album — leave it where it is
    [t] Type a custom name

  Your choice:
```

---

## Collision handling

If the destination folder already exists (e.g. the album was already moved in a previous run), the album is skipped with a `skipped — destination already exists` status and flagged in the report.

---

## Output

Every run saves a timestamped CSV to the `reports\` folder:

| File | Contents |
|---|---|
| `sort_albums_to_artists_dry_TIMESTAMP.csv` | Dry run preview |
| `sort_albums_to_artists_applied_TIMESTAMP.csv` | Results of a live run |

### CSV columns

| Column | Description |
|---|---|
| Album Folder | Name of the album subfolder |
| Artist | Artist name used (from tag or typed) |
| Destination | Full destination path |
| Status | moved / skipped / already correct / error |

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Files

| File | Description |
|---|---|
| `sort_albums_to_artists.py` | Main script |
| `Sort_Albums_To_Artists_Run_Commands.txt` | Quick reference for all commands |
| `reports\` | Per-run CSV reports |
