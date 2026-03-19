# Utilities

Standalone batch rename scripts for common music library housekeeping tasks.

---

## rename_album_folders.py

Reads the album tag from music files inside each subfolder and renames the folder to match. Works at any depth and handles conflicts interactively.

### Setup

Set the two path constants at the top of the script:
```python
DEFAULT_FOLDER = r"C:\Music\Organized"
REPORTS_FOLDER = r"C:\Music\tools\filename_scanner\reports"
```

### Usage

```
python rename_album_folders.py                       # dry run
python rename_album_folders.py --apply               # rename for real
python rename_album_folders.py --pick                # pick folder(s) with a dialog
python rename_album_folders.py --filter              # skip already-correct folders
python rename_album_folders.py --depth 2             # only rename at depth 2 (Artist\Album)
python rename_album_folders.py --filter --depth 2 --apply
```

### Conflict handling

If files in a folder disagree on the album tag, the script shows each unique value with track titles and asks you to choose, type a custom name, or skip.

### Features

- `--pick` — native folder picker dialog, supports multiple folders
- `--filter` — skip folders already correctly named (faster on large libraries)
- `--depth N` — target a specific folder depth only
- Cross-folder collision detection before any renaming
- Illegal Windows characters stripped from proposed names automatically
- CSV report saved after every run

---

## rename_cd_folders.py

Removes the space between CD and number in folder names.

```
CD 1  →  CD1
CD 2  →  CD2
CD 10 →  CD10
```

### Setup

Set the two path constants at the top of the script:
```python
DEFAULT_FOLDER = r"C:\Music\Organized"
REPORTS_FOLDER = r"C:\Music\tools\filename_scanner\reports"
```

### Usage

```
python rename_cd_folders.py               # dry run — shows what would be renamed
python rename_cd_folders.py --apply       # rename for real
python rename_cd_folders.py --path "C:\Music"
python rename_cd_folders.py --apply --path "C:\Music"
```

---

## Files

| File | Description |
|---|---|
| `rename_album_folders.py` | Rename folders to match album tag |
| `rename_cd_folders.py` | Remove space in CD folder names |
| `Rename_Album_Folders_Run_Commands.txt` | Quick reference |
