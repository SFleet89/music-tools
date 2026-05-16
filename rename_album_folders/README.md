# Album Folder Renamer

Reads the `ALBUM` tag from music files in each subfolder and renames the folder to match.

Handles conflicts where files within a folder disagree on the album name — prompts you to choose, with track titles shown per option to help identify the correct album.

---

## Requirements

```
pip install mutagen
```

---

## Usage

```
python rename_album_folders.py                        # dry run, opens folder picker
python rename_album_folders.py --apply                # rename for real
python rename_album_folders.py --pick                 # pick folder with dialog
python rename_album_folders.py --pick --apply
python rename_album_folders.py --path "C:\Music"      # specify folder
python rename_album_folders.py --filter               # skip already-correct folders
python rename_album_folders.py --depth 2              # only rename at depth 2
python rename_album_folders.py --filter --depth 2 --apply
```

---

## .cmd files

| File | What it does |
|---|---|
| `Run - Rename Album Folders (Dry Run).cmd` | Preview renames — nothing is moved |
| `Run - Rename Album Folders (Apply).cmd` | Execute renames |

---

## Flags

| Flag | Description |
|---|---|
| `--apply` | Execute renames (dry run by default) |
| `--pick` | Open folder picker dialog |
| `--path` | Specify root folder on command line |
| `--filter` | Skip folders already correctly named |
| `--depth N` | Only rename folders at depth N (e.g. `--depth 2` for Artist/Album) |

---

## Multi-CD support

Folders containing only CD/Disc/Disk subfolders are detected as multi-CD albums. The **parent folder** is renamed to the album tag; the individual CD subfolders are left untouched.

---

## Conflict handling

- All files agree on album name → renamed automatically
- Files disagree → prompted to choose, with up to 4 track titles shown per option
- No album tag found → folder left unchanged with a warning

---

## Reports

Saved to `rename_album_folders/reports/`. Columns include: Relative Path, Current Name, New Name, Album Tag, Status, Files, Multi-CD.
