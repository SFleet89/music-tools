"""
music_tools_common.py — v2.5 — 2026-05-25
Shared helpers for the Music Tools project.

Provides the project-wide Tier 1 utilities that are otherwise duplicated
in every standalone script:

    SUPPORTED_EXTENSIONS   — set of recognised audio file extensions
    pick_folder(title)     — native Windows folder-picker dialog
    write_csv(rows, path)  — write a UTF-8-BOM CSV report
    load_csv(path)         — read a CSV report into a list of dicts
    get_music_files(folder)— list music files directly in a folder
    sanitise_folder_name(s)— strip characters illegal in Windows folder names
    read_file_tags(path)   — read album/title/tracknumber via Mutagen

    load_config(config_path) — load music_config.json and return the full dict.
                             Defaults to the project-root copy. Raises ValueError on
                             missing file or bad JSON.
    config_organized_folder()
                           — return the 'organized' library path from music_config.json
                             (project root), or None if the config is missing or unset.
    interactive_options(available_options)
                           — show a numbered options menu at script startup and inject
                             chosen flags into sys.argv so the rest of the script reads
                             them normally.  Skips the menu if any listed flag is already
                             present (allows direct flag-passing to bypass the prompt).

    ── SQLite cache helpers ──────────────────────────────────────────────────
    DB_PATH                — Path to shared music_cache.db (next to this file)
    open_db(path)          — open (or create) the database with WAL mode
    init_db(conn)          — create tables and indexes if they don't exist
    migrate_json_to_db(conn, script_dir)
                           — one-time migration from old JSON cache files

Import pattern for scripts in a subfolder one level below the project root:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from music_tools_common import (
        SUPPORTED_EXTENSIONS, pick_folder, write_csv,
        load_csv, get_music_files, sanitise_folder_name, read_file_tags,
    )
"""

import csv
import sqlite3
import sys
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}


# ── Folder picker ──────────────────────────────────────────────────────────────

def pick_folder(title: str = "Select folder") -> "Path | None":
    """
    Open a native Windows folder-picker dialog.

    Returns the selected folder as a Path, or None if the user cancels.
    Exits with an error message if tkinter is unavailable.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("ERROR: tkinter is not available on this system.")
        sys.exit(1)

    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(title=title, parent=root_tk)
    root_tk.destroy()
    return Path(folder) if folder else None


# ── CSV helpers ────────────────────────────────────────────────────────────────

def write_csv(rows: list, output_path, fieldnames: list = None) -> None:
    """
    Write rows to a UTF-8-BOM CSV file with a header row.

    fieldnames — column order. If omitted, inferred from the first row's keys
                 (Python 3.7+ insertion order). Pass FIELDNAMES explicitly when
                 column order matters.
    """
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_csv(csv_path) -> list:
    """Read a UTF-8-BOM CSV file and return a list of row dicts."""
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ── Music file helpers ─────────────────────────────────────────────────────────

def get_music_files(folder: Path) -> list:
    """
    Return all music files directly in folder (non-recursive, sorted).
    Recognised extensions: SUPPORTED_EXTENSIONS.
    """
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def interactive_options(available_options: list) -> None:
    """
    Show a numbered options menu and inject chosen flags into sys.argv.

    Call this BEFORE the flag-parsing lines (DRY_RUN, APPLY, RECURSIVE, etc.)
    in each script.  The rest of the script reads sys.argv as normal, so no
    other code needs to change.

    available_options : list of (flag, description) tuples, e.g.
        [
            ("--apply",     "Apply — make changes for real  (default is dry run)"),
            ("--recursive", "Recursive — scan all subfolders automatically"),
        ]

    If any listed flag is already present in sys.argv the menu is skipped
    entirely, so passing flags directly still works for scripted / power-user use.
    """
    control_flags = [opt[0] for opt in available_options]
    if any(f in sys.argv for f in control_flags):
        return

    print("\n  Run options:")
    for i, (flag, label) in enumerate(available_options, 1):
        print(f"    [{i}]  {label}")
    hint = "e.g. 1" if len(available_options) == 1 else "e.g. 1  or  1,2"
    raw = input(f"\n  Select ({hint}), or press Enter for defaults: ").strip()
    print()

    if not raw:
        return

    for part in raw.replace(" ", "").split(","):
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(available_options):
                flag = available_options[idx][0]
                if flag not in sys.argv:
                    sys.argv.append(flag)


def sanitise_folder_name(name: str) -> str:
    """Remove characters illegal in Windows folder names and trim edge dots/spaces."""
    for ch in r'<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip(". ")


def read_file_tags(path: Path) -> dict:
    """
    Read album, title, and tracknumber from a music file using Mutagen.

    Returns a dict with keys 'album', 'title', 'tracknumber'.
    Values are strings or None if not present / unreadable.
    Requires: pip install mutagen
    """
    result = {"album": None, "title": None, "tracknumber": None}
    try:
        from mutagen import File as MutagenFile
        f = MutagenFile(path, easy=True)
        if f:
            for key in ("album", "title", "tracknumber"):
                val = f.get(key)
                if val:
                    result[key] = val[0].strip() or None
    except Exception:
        pass
    return result


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config(config_path=None) -> dict:
    """
    Load music_config.json and return the full configuration dict.

    config_path — optional explicit path (str or Path). Defaults to
                  music_config.json next to this file (the project root).

    Raises ValueError on missing file or invalid JSON so callers can surface
    a clear error message without needing to handle IO exceptions themselves.
    """
    import json
    cfg_path = Path(config_path) if config_path else Path(__file__).parent / "music_config.json"
    try:
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Config file not found: {cfg_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse config file: {e}")


def config_organized_folder() -> "Path | None":
    """
    Return the organised library folder path from music_config.json, or None.

    The config lives at <project_root>/music_config.json.
    Reads the 'folders.organized' key.  Returns None (silently) if the
    config file is missing, unreadable, or the value is empty — callers
    should fall back to --pick in that case.
    """
    import json
    cfg_path = Path(__file__).parent / "music_config.json"
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        folder = cfg.get("folders", {}).get("organized", "").strip()
        return Path(folder) if folder else None
    except Exception:
        return None


# ── SQLite cache ───────────────────────────────────────────────────────────────

# Shared database lives next to this file (project root).
DB_PATH = Path(__file__).parent / "music_cache.db"

# Current schema version. Increment this whenever a table or column is added.
# init_db() will automatically apply any missing migrations on every run.
SCHEMA_VERSION = 3

# SQL used by init_db — single source of truth for the schema.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata_cache (
    path_str     TEXT PRIMARY KEY,
    mtime        REAL    NOT NULL,
    size         INTEGER NOT NULL,
    filename     TEXT    NOT NULL,
    file_format  TEXT,
    title        TEXT,
    artist       TEXT,
    album_artist TEXT,
    album        TEXT,
    year         TEXT,
    track_number TEXT,
    disc_number  TEXT,
    bitrate      INTEGER,
    sample_rate  INTEGER,
    bit_depth    INTEGER,
    duration     REAL,
    mb_track_id  TEXT,
    mb_album_id  TEXT,
    acoustid_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_meta_artist   ON metadata_cache(artist);
CREATE INDEX IF NOT EXISTS idx_meta_mb_track ON metadata_cache(mb_track_id);

CREATE TABLE IF NOT EXISTS fp_cache (
    path_str    TEXT PRIMARY KEY,
    mtime       REAL    NOT NULL,
    fingerprint TEXT    NOT NULL,
    fp_duration REAL
);

CREATE TABLE IF NOT EXISTS integrity_cache (
    path_str         TEXT PRIMARY KEY,
    mtime            REAL    NOT NULL,
    size             INTEGER NOT NULL,
    integrity_status TEXT    NOT NULL,
    integrity_detail TEXT,
    checked_at       TEXT    NOT NULL
);
"""

# Migrations: keyed by the version they bring the DB UP TO.
# Add a new entry here whenever SCHEMA_VERSION is incremented.
_MIGRATIONS = {
    3: [
        # v3: acoustid_id column added to metadata_cache (2026-05-21)
        "ALTER TABLE metadata_cache ADD COLUMN acoustid_id TEXT",
    ],
    2: [
        # v2: integrity_cache table (added 2026-05-18)
        """CREATE TABLE IF NOT EXISTS integrity_cache (
            path_str         TEXT PRIMARY KEY,
            mtime            REAL    NOT NULL,
            size             INTEGER NOT NULL,
            integrity_status TEXT    NOT NULL,
            integrity_detail TEXT,
            checked_at       TEXT    NOT NULL
        )""",
    ],
}

# Column order for metadata_cache bulk inserts (matches _SCHEMA_SQL).
_META_COLS = (
    "path_str", "mtime", "size", "filename", "file_format",
    "title", "artist", "album_artist", "album", "year",
    "track_number", "disc_number", "bitrate", "sample_rate",
    "bit_depth", "duration", "mb_track_id", "mb_album_id",
    "acoustid_id",
)


def open_db(db_path: "Path | None" = None) -> sqlite3.Connection:
    """
    Open (or create) the cache database.

    Uses WAL journal mode so reads and writes can overlap safely —
    important when build_fp_cache and find_music_duplicates run close
    together without full re-scans.
    """
    conn = sqlite3.connect(str(db_path or DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create tables and indexes if they don't exist, then apply any pending
    migrations to bring an older database up to the current schema version.
    Safe to call on every run.
    """
    conn.executescript(_SCHEMA_SQL)
    conn.commit()

    # Read the stored version (0 if the table is empty / first run).
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    db_version = row[0] if row else 0

    if db_version < SCHEMA_VERSION:
        for ver in range(db_version + 1, SCHEMA_VERSION + 1):
            for sql in _MIGRATIONS.get(ver, []):
                try:
                    conn.execute(sql)
                except Exception:
                    pass  # Table may already exist on a fresh DB — safe to skip
        conn.commit()

    # Always write/update the version record.
    if row:
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    else:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def upsert_metadata_rows(conn: sqlite3.Connection, rows: list) -> None:
    """
    Bulk-upsert metadata rows into metadata_cache.

    Each row must be a dict whose keys are the _META_COLS column names.
    Uses INSERT OR REPLACE so re-scanned files overwrite stale entries.
    """
    placeholders = ", ".join(f":{c}" for c in _META_COLS)
    sql = (
        f"INSERT OR REPLACE INTO metadata_cache ({', '.join(_META_COLS)}) "
        f"VALUES ({placeholders})"
    )
    conn.executemany(sql,
    rows)
    conn.commit()


def migrate_json_to_db(conn: sqlite3.Connection, script_dir: Path) -> tuple:
    """
    One-time migration of the legacy JSON cache files to the shared SQLite DB.

    Looks for music_cache.json (metadata) and music_fp_cache.json
    (fingerprints) in script_dir.  Each file is read, its entries are
    upserted into the appropriate SQLite table, and the JSON file is renamed
    to <name>.json.migrated so it is not processed again on subsequent runs.

    Returns (meta_rows_migrated, fp_rows_migrated).
    """
    import json as _json

    meta_count = 0
    fp_count   = 0

    # ── metadata cache ─────────────────────────────────────────────────────
    meta_json = script_dir / "music_cache.json"
    if meta_json.exists():
        try:
            raw = _json.loads(meta_json.read_text(encoding='utf-8'))
            rows = []
            for path_str, entry in raw.items():
                if not isinstance(entry, dict):
                    continue
                row = {col: entry.get(col) for col in _META_COLS}
                row["path_str"] = path_str
                row.setdefault("mtime",    0.0)
                row.setdefault("size",     0)
                row.setdefault("filename", Path(path_str).name)
                rows.append(row)
            if rows:
                upsert_metadata_rows(conn, rows)
                meta_count = len(rows)
                print(f"  Migrated {meta_count:,} metadata entries from music_cache.json")
            meta_json.rename(meta_json.with_suffix('.json.migrated'))
        except Exception as exc:
            print(f"  WARNING: could not migrate music_cache.json: {exc}")

    # ── fingerprint cache ───────────────────────────────────────────────────
    fp_json = script_dir / "music_fp_cache.json"
    if fp_json.exists():
        try:
            raw = _json.loads(fp_json.read_text(encoding='utf-8'))
            sql = (
                "INSERT OR REPLACE INTO fp_cache "
                "(path_str, mtime, fingerprint, fp_duration) "
                "VALUES (:path_str, :mtime, :fingerprint, :fp_duration)"
            )
            rows = []
            for path_str, entry in raw.items():
                if not isinstance(entry, dict):
                    continue
                rows.append({
                    "path_str":    path_str,
                    "mtime":       entry.get("mtime", 0.0),
                    "fingerprint": entry.get("fingerprint", ""),
                    "fp_duration": entry.get("duration"),
                })
            rows = [r for r in rows if r["fingerprint"]]
            if rows:
                conn.executemany(sql, rows)
                conn.commit()
                fp_count = len(rows)
                print(f"  Migrated {fp_count:,} fingerprint entries from music_fp_cache.json")
            fp_json.rename(fp_json.with_suffix('.json.migrated'))
        except Exception as exc:
            print(f"  WARNING: could not migrate music_fp_cache.json: {exc}")

    return (meta_count, fp_count)
