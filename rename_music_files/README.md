# rename_music_files.py — v1.0

Renames audio files using a FileBot-style template string built from embedded tags.
Nothing is renamed until you add `--apply`. Every run saves a CSV report.

---

## What it does

Walks a folder recursively, reads the tags of every MP3, FLAC, AAC, and M4A file,
and renames each one according to the template you provide.

Files with missing required tags are **skipped** (left untouched) and logged to the
CSV so you can fix their tags first and re-run.

---

## Template variables

| Variable       | Tag used              | Example output  |
|----------------|-----------------------|-----------------|
| `{t}`          | Title                 | Perfect Day     |
| `{n}`          | Album artist (→ artist if absent) | Artist A |
| `{artist}`     | Track artist          | Artist A        |
| `{album}`      | Album                 | The Album       |
| `{pi}`         | Track number (raw)    | 3               |
| `{pi.pad(2)}`  | Track number, 2-digit | 03              |
| `{pi.pad(3)}`  | Track number, 3-digit | 003             |
| `{y}`          | Year                  | 2009            |
| `{af}`         | Audio format          | mp3 / flac      |
| `{kbps}`       | Bitrate (rounded)     | 320             |
| `{disc}`       | Disc number           | 1               |

**Default format:** `{pi.pad(2)} - {t}`  
→ `01 - Perfect Day.mp3`

---

## Usage

```
python rename_music_files.py --pick
python rename_music_files.py --pick --apply
python rename_music_files.py --path "E:\Music\Album" --format "{n} - {t}"
python rename_music_files.py --path "E:\Music" --format "{pi.pad(2)} - {t}" --apply
```

Or double-click one of the `.cmd` launchers. Both use `--pick` to open a folder
dialog — neither has a hardcoded path.

---

## Flags

| Flag              | Effect                                                   |
|-------------------|----------------------------------------------------------|
| `--pick`          | Open a folder picker dialog                              |
| `--path "…"`      | Specify the folder directly                              |
| `--format "…"`    | Template string (default: `{pi.pad(2)} - {t}`)          |
| `--apply`         | Rename for real (dry run is the default)                 |
| `--no-confirm`    | Skip the confirmation prompt (for scripted use)          |

---

## Output (reports folder)

Every run saves a timestamped CSV to `rename_music_files/reports/`:

| Column          | Contents                                          |
|-----------------|---------------------------------------------------|
| `status`        | `would_rename` / `renamed` / `skipped` / `collision` / `already_correct` / `error` |
| `original_name` | Filename before renaming                          |
| `new_name`      | Filename that would be / was applied              |
| `missing_tags`  | Which tags were absent (for skipped files)        |
| `original_path` | Full path to the file                             |
| `title` … `kbps`| Tag snapshot at the time of the run               |

---

## Status values

| Status            | Meaning                                                  |
|-------------------|----------------------------------------------------------|
| `would_rename`    | Dry run — this file would be renamed                     |
| `renamed`         | Apply mode — file successfully renamed                   |
| `already_correct` | Filename already matches the template — no change needed |
| `skipped`         | One or more required tags missing — left untouched       |
| `collision`       | Target filename already exists — left untouched          |
| `error`           | Rename failed (permissions, locked file, etc.)           |

---

## Format examples

| Template                        | Example output                    |
|---------------------------------|-----------------------------------|
| `{pi.pad(2)} - {t}`             | `01 - Perfect Day.mp3`            |
| `{artist} - {t}`                | `Artist A - Perfect Day.mp3`      |
| `{pi.pad(2)} - {artist} - {t}` | `01 - Artist A - Perfect Day.mp3` |
| `{pi.pad(2)} - {n} - {t}`      | `01 - Artist A - Perfect Day.mp3` |
| `{y} - {t}`                     | `2009 - Perfect Day.mp3`          |

---

## Requirements

```
pip install mutagen
```

---

## Notes

- Files are processed **recursively** — all subfolders are included.
- Track numbers stored as `3/12` are automatically normalised to `3`.
- Years stored as `2009-06-15` are trimmed to `2009`.
- Characters illegal in Windows filenames are stripped from the output.
- `shutil.move` is used for all renames — safe across drives.
- In apply mode, a confirmation prompt shows the count before any files are touched.
