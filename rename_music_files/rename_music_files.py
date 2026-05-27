"""
rename_music_files.py — v1.2
Renames audio files using a FileBot-style template string.

Template variables:
  {t}          Title tag
  {n}          Album artist tag (falls back to artist if absent)
  {artist}     Artist tag
  {album}      Album tag
  {pi}         Track number (raw, e.g. "3")
  {pi.pad(N)}  Track number zero-padded to N digits (e.g. "03")
  {y}          Year tag
  {af}         Audio format / extension  (mp3, flac, m4a, aac)
  {kbps}       Bitrate in kbps (rounded to nearest 10)
  {disc}       Disc number tag

Default format: {pi.pad(2)} - {t}
  e.g. "01 - Perfect Day.mp3"

Usage:
  python rename_music_files.py --pick
  python rename_music_files.py --pick --apply
  python rename_music_files.py --path "E:\\Music\\Album" --format "{n} - {t}"
  python rename_music_files.py --path "E:\\Music" --format "{pi.pad(2)} - {t}" --apply

Flags:
  --pick            Open a folder picker dialog
  --path "..."      Specify folder directly
  --format "..."    Template string (default: {pi.pad(2)} - {t})
  --apply           Rename files for real (dry run is the default)
  --no-confirm      Skip the confirmation prompt in apply mode
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS, pick_folder, write_csv,
    interactive_options,
)

# ── Mutagen imports ────────────────────────────────────────────────────────────
try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, ID3NoHeaderError
except ImportError:
    print("ERROR: mutagen is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"
DEFAULT_FORMAT = "{pi.pad(2)} - {t}"

# Characters illegal in Windows filenames
_ILLEGAL_CHARS = r'<>:"/\\|?*'

# Matches {variable} and {variable.pad(N)}
_VAR_RE = re.compile(r"\{(\w+)(?:\.pad\((\d+)\))?\}")


# =============================================================================
#  Tag reading
# =============================================================================

def _first(tag_dict, *keys):
    """Return the first non-empty value from a mutagen tag dict."""
    for k in keys:
        val = tag_dict.get(k)
        if val:
            v = str(val[0]).strip()
            if v:
                return v
    return None


def _read_id3_fallback(path):
    """
    Fallback for MP3 files where MutagenFile(easy=True) fails because
    the MPEG sync frame is missing or malformed.
    """
    try:
        raw = ID3(str(path))
    except (ID3NoHeaderError, Exception):
        return None

    easy = {}
    frame_map = {
        "TIT2": "title",
        "TPE1": "artist",
        "TPE2": "albumartist",
        "TALB": "album",
        "TRCK": "tracknumber",
        "TDRC": "date",
        "TPOS": "discnumber",
    }
    for frame_id, easy_key in frame_map.items():
        frame = raw.get(frame_id)
        if frame and hasattr(frame, "text") and frame.text:
            easy[easy_key] = [str(frame.text[0])]
    return easy if easy else None


def read_tags(path):
    """
    Read all template-relevant tags from an audio file.
    Returns a dict with keys: t, n, artist, album, pi, y, af, kbps, disc.
    """
    result = {k: None for k in ("t", "n", "artist", "album", "pi", "y", "af", "kbps", "disc")}
    result["af"] = path.suffix.lower().lstrip(".")

    f = None
    info_obj = None
    try:
        f = MutagenFile(path, easy=True)
        info_obj = getattr(f, "info", None) if f else None
    except Exception:
        if path.suffix.lower() == ".mp3":
            f = _read_id3_fallback(path)

    if f is None:
        return result

    try:
        result["t"]      = _first(f, "title")
        result["artist"] = _first(f, "artist")
        result["n"]      = _first(f, "albumartist", "album_artist") or result["artist"]
        result["album"]  = _first(f, "album")
        result["y"]      = _first(f, "date", "year")
        result["disc"]   = _first(f, "discnumber", "disc")

        raw_pi = _first(f, "tracknumber")
        if raw_pi:
            result["pi"] = raw_pi.split("/")[0].strip().lstrip("0") or "0"

        if result["y"] and len(result["y"]) > 4:
            m = re.search(r"\d{4}", result["y"])
            result["y"] = m.group() if m else result["y"][:4]

        if result["disc"]:
            result["disc"] = result["disc"].split("/")[0].strip()

        if info_obj:
            br = getattr(info_obj, "bitrate", None)
            if br:
                result["kbps"] = str(round(br / 1000 / 10) * 10)

    except Exception:
        pass

    return result


# =============================================================================
#  Template rendering
# =============================================================================

def render_template(template, tags):
    """
    Render a template string using the tag dict.
    Returns (rendered_name, missing_vars).
    """
    missing = []

    def replace(m):
        var   = m.group(1)
        pad_n = m.group(2)
        value = tags.get(var)
        if value is None:
            missing.append(var)
            return ""
        if pad_n:
            try:
                return str(int(value)).zfill(int(pad_n))
            except ValueError:
                return value
        return value

    rendered = _VAR_RE.sub(replace, template)

    if missing:
        return None, missing

    return rendered.strip(), []


def sanitise_filename(name):
    """Strip characters illegal in Windows filenames and trim edge spaces/dots."""
    for ch in _ILLEGAL_CHARS:
        name = name.replace(ch, "")
    name = re.sub(r"  +", " ", name)
    return name.strip(". ")


# =============================================================================
#  Core rename logic
# =============================================================================

def collect_files(root):
    """Recursively collect all supported audio files under root, sorted."""
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def plan_renames(files, template):
    """
    Build a rename plan for every file.

    Status values:
      would_rename    — file will be renamed (dry run)
      already_correct — filename already matches template
      skipped         — required tag(s) missing
      collision       — target filename already taken by a different file
    """
    rows = []
    for path in files:
        tags = read_tags(path)
        new_stem, missing = render_template(template, tags)

        row = {
            "original_path": str(path),
            "original_name": path.name,
            "new_name":      "",
            "status":        "",
            "missing_tags":  "",
            "title":         tags.get("t")      or "",
            "artist":        tags.get("artist") or "",
            "album_artist":  tags.get("n")      or "",
            "album":         tags.get("album")  or "",
            "track":         tags.get("pi")     or "",
            "year":          tags.get("y")      or "",
            "format":        tags.get("af")     or "",
            "kbps":          tags.get("kbps")   or "",
        }

        if missing:
            row["status"]       = "skipped"
            row["missing_tags"] = ", ".join(missing)
            rows.append(row)
            continue

        new_name = sanitise_filename(new_stem) + path.suffix.lower()
        new_path = path.parent / new_name

        if path.name == new_name:
            row["new_name"] = new_name
            row["status"]   = "already_correct"
        elif new_path.exists() and new_path != path:
            row["new_name"] = new_name
            row["status"]   = "collision"
        else:
            row["new_name"] = new_name
            row["status"]   = "would_rename"

        rows.append(row)

    return rows


def apply_renames(rows, progress_callback=None, log_callback=None):
    """Execute renames for all rows with status 'would_rename'."""
    log = log_callback or print
    to_do = [r for r in rows if r["status"] == "would_rename"]
    for i, row in enumerate(to_do):
        if progress_callback:
            progress_callback(i + 1, len(to_do), row["original_name"])
        src = Path(row["original_path"])
        dst = src.parent / row["new_name"]
        try:
            shutil.move(str(src), str(dst))
            row["status"] = "renamed"
        except Exception as e:
            row["status"]       = "error"
            row["missing_tags"] = str(e)
            log(f"  [ERROR] {row['original_name']}: {e}")
    return rows


# =============================================================================
#  Reporting
# =============================================================================

FIELDNAMES = [
    "status", "original_name", "new_name",
    "missing_tags", "original_path",
    "title", "artist", "album_artist", "album", "track", "year", "format", "kbps",
]


def write_report(rows, dry_run) -> Path:
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "dry" if dry_run else "applied"
    path   = REPORTS_FOLDER / f"rename_music_files_{suffix}_{ts}.csv"
    write_csv(rows, path, fieldnames=FIELDNAMES)
    return path


def print_summary(rows, dry_run):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    label = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n{'─' * 50}")
    print(f"  {label} SUMMARY")
    print(f"{'─' * 50}")
    for status, count in sorted(counts.items()):
        print(f"  {status:<20} {count:>5}")
    print(f"  {'TOTAL':<20} {len(rows):>5}")

    skipped    = [r for r in rows if r["status"] == "skipped"]
    collisions = [r for r in rows if r["status"] == "collision"]

    if skipped:
        print(f"\n  Skipped (missing tags):")
        for r in skipped[:10]:
            print(f"    {r['original_name']}  ->  missing: {r['missing_tags']}")
        if len(skipped) > 10:
            print(f"    ... and {len(skipped) - 10} more (see report)")

    if collisions:
        print(f"\n  Collisions (target name already exists):")
        for r in collisions[:10]:
            print(f"    {r['original_name']}  ->  {r['new_name']}")
        if len(collisions) > 10:
            print(f"    ... and {len(collisions) - 10} more (see report)")


# =============================================================================
#  CORE LOGIC  ← GUI calls this directly
# =============================================================================

def run_rename_music_files(
    folder: Path,
    apply: bool = False,
    template: str = DEFAULT_FORMAT,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan folder and rename music files using a template string.

    Args:
        folder:            Root folder to scan recursively.
        apply:             False = dry run; True = rename files.
        template:          FileBot-style template string (default: {pi.pad(2)} - {t}).
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: renamed, would_rename, skipped, collisions, errors,
              results (list of row dicts), report_path (Path)

    Raises:
        ValueError: folder does not exist or is not a directory.
        ValueError: template contains unknown variables.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    known_vars = {"t", "n", "artist", "album", "pi", "y", "af", "kbps", "disc"}
    used_vars  = {m.group(1) for m in _VAR_RE.finditer(template)}
    unknown    = used_vars - known_vars
    if unknown:
        raise ValueError(f"Unknown template variable(s): {', '.join(sorted(unknown))}")

    files = collect_files(folder)
    if not files:
        log("  No supported audio files found.")
        return {"renamed": 0, "would_rename": 0, "skipped": 0,
                "collisions": 0, "errors": 0, "results": [], "report_path": None}

    log(f"  Found {len(files):,} audio file(s).")

    if progress_callback:
        progress_callback(0, len(files), "Planning renames...")

    rows = plan_renames(files, template)

    to_rename = [r for r in rows if r["status"] == "would_rename"]
    log(f"  {len(to_rename):,} file(s) would be renamed.")

    if apply and to_rename:
        rows = apply_renames(rows, progress_callback=progress_callback, log_callback=log)

    report_path = write_report(rows, dry_run=not apply)
    log(f"  Report saved: {report_path}")

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "renamed":      counts.get("renamed", 0),
        "would_rename": counts.get("would_rename", 0),
        "skipped":      counts.get("skipped", 0),
        "collisions":   counts.get("collision", 0),
        "errors":       counts.get("error", 0),
        "results":      rows,
        "report_path":  report_path,
    }


# =============================================================================
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# =============================================================================

def main():
    interactive_options([])

    dry_run    = "--apply"      not in sys.argv
    pick_dir   = "--pick"       in sys.argv
    no_confirm = "--no-confirm" in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )
    _format_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--format" and i + 1 < len(sys.argv)),
        None,
    )
    template = _format_flag or DEFAULT_FORMAT

    print("Music File Renamer  v1.2")
    print("=" * 50)
    mode = "DRY RUN -- no files will be renamed" if dry_run else "APPLY -- files will be renamed"
    print(f"  Mode   : {mode}")
    print(f"  Format : {template}")

    # ── Folder selection ──────────────────────────────────────────────────────
    if _path_flag:
        root = Path(_path_flag.strip('"'))
    elif pick_dir:
        root = pick_folder("Select folder to rename music files in")
        if not root:
            print("No folder selected. Exiting.")
            sys.exit(0)
    else:
        print("ERROR: No folder specified. Use --pick or --path.")
        sys.exit(1)

    if not root.exists() or not root.is_dir():
        print(f"\nERROR: Folder not found: {root}")
        sys.exit(1)

    print(f"  Folder : {root}")

    # ── Validate template ─────────────────────────────────────────────────────
    known_vars = {"t", "n", "artist", "album", "pi", "y", "af", "kbps", "disc"}
    used_vars  = {m.group(1) for m in _VAR_RE.finditer(template)}
    unknown    = used_vars - known_vars
    if unknown:
        print(f"\nERROR: Unknown template variable(s): {', '.join(sorted(unknown))}")
        print(f"  Known variables: {', '.join(sorted(known_vars))}")
        sys.exit(1)

    # ── Scan + plan ───────────────────────────────────────────────────────────
    print("\nScanning ...")
    files = collect_files(root)
    if not files:
        print("  No supported audio files found.")
        sys.exit(0)
    print(f"  Found {len(files):,} audio file(s).")

    rows      = plan_renames(files, template)
    to_rename = [r for r in rows if r["status"] == "would_rename"]
    print(f"  {len(to_rename):,} file(s) would be renamed.")

    if to_rename:
        print()
        for r in to_rename[:20]:
            print(f"  {r['original_name']}")
            print(f"    -> {r['new_name']}")
        if len(to_rename) > 20:
            print(f"  ... and {len(to_rename) - 20} more (see report)")

    # ── Apply ─────────────────────────────────────────────────────────────────
    if not dry_run and to_rename:
        if not no_confirm:
            print()
            confirm = input(f"  Rename {len(to_rename):,} file(s)? (y/n): ").strip().lower()
            while confirm not in ("y", "n"):
                confirm = input("  Please enter y or n: ").strip().lower()
            if confirm != "y":
                print("  Aborted. Nothing renamed.")
                report_path = write_report(rows, dry_run=True)
                print(f"\n  Plan saved to: {report_path}")
                sys.exit(0)

        print("\nRenaming ...")
        rows = apply_renames(rows)

    # ── Report ────────────────────────────────────────────────────────────────
    report_path = write_report(rows, dry_run=dry_run)
    print_summary(rows, dry_run=dry_run)
    print(f"\n  Report : {report_path}")


if __name__ == "__main__":
    main()
