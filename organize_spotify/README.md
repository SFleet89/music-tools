# organize_spotify

Reads audio tags from Spotify/Streamrip downloads (organised by playlist folders) and
re-organises them into an **AlbumArtist / Album** folder structure inside a staging folder
of your choice. Nothing is moved until you confirm with `--apply`.

---

## What it does

1. Walks every audio file in your source folder (and its subfolders)
2. Reads the `albumartist`, `album`, and `title` tags using mutagen
3. Plans a move to: `<dest>\<AlbumArtist>\<Album>\<filename>`
4. In dry-run mode, shows you the plan and saves a CSV report — no files are touched
5. In apply mode, asks for confirmation, then moves the files and saves a report

Files with missing tags fall back to `Unknown Artist` / `Unknown Album`.
If a filename collision occurs in the destination, a `(1)`, `(2)` … suffix is appended.

---

## Usage

**Dry run (safe — no changes):**
```
python organize_spotify.py --pick-source --pick-dest
```

**Apply (moves files):**
```
python organize_spotify.py --pick-source --pick-dest --apply
```

**Supply paths directly:**
```
python organize_spotify.py --path-source "C:\...\Streamrip" --path-dest "C:\...\Organized" --apply
```

Or just double-click one of the `.cmd` launchers in this folder.

---

## Flags

| Flag | Description |
|------|-------------|
| `--pick-source` | Open a folder dialog to select the Spotify/Streamrip source |
| `--path-source "C:\..."` | Supply source path directly |
| `--pick-dest` | Open a folder dialog to select the staging destination |
| `--path-dest "C:\..."` | Supply destination path directly |
| `--apply` | Actually move files (default: dry run) |

If `--pick-dest` / `--path-dest` are both omitted, the destination defaults to
`<source>\Organized\`.

---

## Output

A timestamped CSV is saved to `<script_folder>\reports\` after every run:

| Column | Description |
|--------|-------------|
| `status` | `dry_run`, `moved`, or `error` |
| `source_file` | Full path of the original file |
| `destination` | Full path where the file was (or would be) moved |
| `albumartist` | Tag value used for folder name |
| `album` | Tag value used for folder name |
| `title` | Track title from tags |
| `note` | Any warnings (tag errors, collision resolutions) |

---

## Requirements

```
pip install mutagen
```

Python 3.10+ recommended (uses `Path.is_relative_to`).
