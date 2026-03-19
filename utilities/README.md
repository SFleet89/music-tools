# Album Folder Renamer

Reads the album tag from music files inside each subfolder and renames the folder to match. Works at any depth — flat libraries, Artist/Album structures, or anything in between.

Nothing is renamed until you confirm. Dry run by default.

---

## How it works

For each folder that contains music files directly inside it, the script reads the album tag from every file and determines the correct folder name. It handles three cases:

- **All files agree** — renames automatically (after your final confirm)
- **Files disagree** — prompts you to choose, showing track titles for each option so you can identify the right album
- **No album tag found** — leaves the folder unchanged with a warning

Before any renaming happens, the script checks for cross-folder collisions — two different folders that would end up with the same name under the same parent. Those are flagged and skipped.

---

## Requirements

```
pip install mutagen
```

`tkinter` is required for the `--pick` dialog and is built into most Python installations — no separate install needed.

---

## Usage

```
python rename_album_folders.py                       # dry run on default folder
python rename_album_folders.py --apply               # rename for real
python rename_album_folders.py --pick                # pick folder(s) with a dialog
python rename_album_folders.py --pick --apply        # pick and rename
python rename_album_folders.py --path "C:\Music"     # override folder path
python rename_album_folders.py --filter              # skip already-correct folders
python rename_album_folders.py --depth 2             # only rename at depth 2
```

Flags can be combined freely:

```
python rename_album_folders.py --filter --depth 2 --apply
python rename_album_folders.py --pick --filter --apply
python rename_album_folders.py --path "C:\Music" --filter --depth 2 --apply
```

---

## Flags

| Flag | Description |
|---|---|
| `--apply` | Rename for real. Without this, the script is always a dry run. |
| `--pick` | Open a native folder-picker dialog. You can pick multiple folders — it asks after each selection whether to add another. |
| `--path PATH` | Override the default root folder path. |
| `--filter` | Skip folders whose current name already matches the album tag. Speeds up subsequent runs on large libraries where most folders are already correct. |
| `--depth N` | Only scan folders exactly N levels deep relative to the root. Use `--depth 2` for a classic Artist/Album structure (Artist\ = depth 1, Artist\Album\ = depth 2). |

---

## Recommended workflow

```
# Step 1 — dry run to preview what would change
python rename_album_folders.py --filter --depth 2

# Step 2 — rename for real
python rename_album_folders.py --filter --depth 2 --apply
```

On large libraries, `--filter` and `--depth` together make the scan significantly faster by skipping folders that don't need attention.

---

## Conflict resolution

When files inside a folder have different album tags, the script prompts you interactively:

```
  CONFLICT in: 2008 - End Titles
  Path       : C:\Music\U.N.K.L.E\2008 - End Titles
  2 different album tags found:

    [1] End Titles... Redux  (14 file(s))
          1. Intro
          2. Looking for the Rain
          3. Reign
          4. Money and Run
          ... and 10 more

    [2] End Titles  (3 file(s))
          15. Outro
          16. Hidden Track
          17. Bonus

    [s] Skip this folder
    [t] Type a custom name

  Your choice:
```

Enter the number of the album you want to use, `s` to skip, or `t` to type a custom name.

---

## Collision detection

If two folders in the same parent directory would rename to the same name, both are flagged and skipped with a warning before any renaming happens:

```
  WARNING: 1 naming collision(s) detected:
    Target name: Best Of  (in C:\Music\Queen)
      Greatest Hits
      Best Of Queen
```

---

## Output

Every run saves a timestamped CSV to your reports folder:

| File | Contents |
|---|---|
| `rename_album_folders_dry_TIMESTAMP.csv` | Dry run preview |
| `rename_album_folders_applied_TIMESTAMP.csv` | Results of a live run |

### CSV columns

| Column | Description |
|---|---|
| Relative Path | Folder path relative to the scanned root |
| Current Name | Folder name before the run |
| New Name | Proposed or applied new name |
| Album Tag | Album tag read from the files |
| Status | What happened (renamed, already correct, skipped, error, etc.) |
| Files | Number of music files in the folder |

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Files

| File | Description |
|---|---|
| `rename_album_folders.py` | Main script |
| `Rename_Album_Folders_Run_Commands.txt` | Quick reference for all commands |
| `reports\rename_album_folders_*.csv` | Per-run reports |
