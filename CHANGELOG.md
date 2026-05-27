# Changelog — Project Root / Shared Modules

---

## music_tools_common.py

### v2.5 — 2026-05-25

#### Added
- `load_config(config_path=None) -> dict` — shared JSON reader for `music_config.json`. Defaults to the project-root copy. Raises `ValueError` on missing file or invalid JSON. All scripts that previously had their own local `load_config()` now import this instead.

#### Fixed
- Reconstructed truncated `migrate_json_to_db()` function body — the file had been silently truncated mid-function, leaving `upsert_metadata_rows()` incomplete and `migrate_json_to_db()` missing entirely. Both functions restored.

---

### v2.4 — 2026-05-23

#### Added
- `interactive_options(available_options)` — presents a numbered menu at script startup and injects chosen flags into `sys.argv` so the rest of the script reads them normally. Skips the menu if any listed flag is already present (allows direct flag-passing to bypass the prompt). Used by all scripts for the interactive launch mode.

---

### v2.3 — 2026-05-22

#### Changed
- `config_organized_folder()` now reads `music_config.json` from the project root instead of `duplicate_finder/music_config.json`. Updated docstring and inline comment to match.

---

### v2.2 — 2026-05-22

#### Added
- `config_organized_folder()` — reads `folders.organized` from `music_config.json` and returns a `Path`. Returns `None` on any error. Used by scripts as a zero-config fallback when neither `--path` nor `--pick` is given.

---

### v2.1 — 2026-05-18

#### Added
- Schema versioning: `schema_version` table, `SCHEMA_VERSION = 2` constant, migration framework in `init_db`.
- `integrity_cache` table added to schema (used by `check_music_integrity.py`).

---

### v2.0 — 2026-05-17

#### Added
- **SQLite cache layer** — shared `music_cache.db` (WAL mode) replaces per-script JSON files.
  - `DB_PATH` — resolved `Path` pointing to `music_cache.db` next to this file (project root).
  - `open_db(db_path=None)` — opens (or creates) the database with `row_factory = sqlite3.Row`, WAL journal mode, and `synchronous=NORMAL` for safe concurrent reads/writes.
  - `init_db(conn)` — idempotent `CREATE TABLE IF NOT EXISTS` for both `metadata_cache` (18 columns) and `fp_cache` (4 columns), plus indexes on `artist` and `mb_track_id`. Safe to call on every run.
  - `upsert_metadata_rows(conn, rows)` — bulk `INSERT OR REPLACE` into `metadata_cache` using named placeholders; accepts a list of dicts.
  - `migrate_json_to_db(conn, script_dir)` — one-time migration: reads `music_cache.json` and `music_fp_cache.json`, imports all entries into SQLite, renames the originals to `.json.bak`. Returns `(meta_count, fp_count)`.
- **Expanded metadata schema** — `metadata_cache` now stores: `path_str`, `mtime`, `size`, `filename`, `file_format`, `title`, `artist`, `album_artist`, `album`, `year`, `track_number`, `disc_number`, `bitrate`, `sample_rate`, `bit_depth`, `duration`, `mb_track_id`, `mb_album_id`.
- `_META_COLS` tuple — canonical column order for bulk inserts; single source of truth for the schema.

#### Changed
- Added `import sqlite3` to the module imports.
- Module docstring updated to document all new public symbols.

### v1.0 — 2026-05-17 (initial extraction)

#### Added
- Initial extraction from project scripts into a shared module.
- `SUPPORTED_EXTENSIONS` — set of recognised audio file extensions (`.mp3`, `.flac`, `.aac`, `.m4a`).
- `pick_folder(title)` — native Windows folder-picker dialog via tkinter.
- `write_csv(rows, path, fieldnames)` — UTF-8-BOM CSV writer.
- `load_csv(path)` — UTF-8-BOM CSV reader returning list of dicts.
- `get_music_files(folder)` — sorted list of music files directly in a folder (non-recursive).
- `sanitise_folder_name(s)` — strips characters illegal in Windows folder names.
- `read_file_tags(path)` — reads `album`, `title`, `tracknumber` via Mutagen.
