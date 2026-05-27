"""
Sort By Artist  v1.3
====================
Sorts audio files from a flat folder into artist subfolders.

Reads each file's tags first (mutagen), then falls back to parsing
"Artist - Title" from the filename. Featured-artist credits are stripped
to keep the main artist name only.

Files with no detectable artist, or whose artist is a "Various Artists"
variant, are left in place (not moved).

  Dry run by default.  Add --apply to execute moves.

Usage:
    python sort_by_artist.py --pick              # folder dialog, dry run
    python sort_by_artist.py --pick --apply      # folder dialog, move files
    python sort_by_artist.py --path "C:\\folder" # use specific folder, dry run
    python sort_by_artist.py --path "C:\\folder" --apply
"""

import sys
import re
import shutil
from pathlib import Path
from datetime import datetime

# ── Shared project imports ─────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS,
    pick_folder,
    write_csv,
    sanitise_folder_name,
    interactive_options,
)

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# ── Constants ──────────────────────────────────────────────────────────────────
SCRIPT_NAME = "sort_by_artist"
VERSION     = "1.3"

FIELDNAMES = ["file", "artist_found", "artist_source", "destination", "status", "notes"]

# Regex that matches featured-artist suffixes in any form:
#   ft. / feat. / featuring / with  (optionally wrapped in parentheses or brackets)
_FEAT_RE = re.compile(
    r"\s*[\(\[]?\s*(?:ft\.?|feat\.?|featuring|with)\b.*",
    re.IGNORECASE,
)

# Artist names that mean "no real artist" — leave these files in place
_VARIOUS_ARTISTS = {
    "various artists",
    "various",
    "va",
    "v.a.",
    "v.a",
}


# ── Artist detection ───────────────────────────────────────────────────────────

def _strip_featured(name: str) -> str:
    """Remove featured-artist credits from an artist string.

    Guard: if the regex would consume the entire string (i.e. the name itself
    starts with ft./feat.), return the original — it's a real name, not a credit.
    """
    stripped = _FEAT_RE.sub("", name).strip(" ,;-")
    return stripped if stripped else name


def _normalise_artist(raw: str) -> str:
    """Strip featured artists and collapse whitespace."""
    cleaned = _strip_featured(raw)
    return " ".join(cleaned.split())


def _is_various(artist: str) -> bool:
    return artist.strip().lower() in _VARIOUS_ARTISTS


def _artist_from_tags(file_path: Path) -> str | None:
    """Return the artist tag from the file, or None if not found / empty."""
    try:
        import mutagen
        audio = mutagen.File(file_path, easy=True)
        if audio is None:
            return None
        artist_list = audio.get("artist") or audio.get("albumartist")
        if artist_list:
            raw = str(artist_list[0]).strip()
            if raw:
                return _normalise_artist(raw)
    except Exception:
        pass
    return None


def _artist_from_filename(file_path: Path) -> str | None:
    """
    Attempt to parse 'Artist - Title' from the filename stem.
    Returns None if the pattern is not recognised.
    """
    stem = file_path.stem
    # Must have a ' - ' separator; first token is the artist
    if " - " in stem:
        candidate = stem.split(" - ", 1)[0].strip()
        if candidate:
            return _normalise_artist(candidate)
    return None


def detect_artist(file_path: Path) -> tuple[str | None, str]:
    """
    Return (artist_name, source) where source is 'tag', 'filename', or 'none'.
    artist_name is None when no artist could be determined.

    If the tag says "Various Artists" (or a known variant), fall back to
    filename parsing before giving up — the tag may be wrong/generic while
    the filename still encodes the real artist.
    """
    artist = _artist_from_tags(file_path)
    if artist and not _is_various(artist):
        return artist, "tag"

    artist = _artist_from_filename(file_path)
    if artist and not _is_various(artist):
        return artist, "filename"

    return None, "none"


# ── File scanning ──────────────────────────────────────────────────────────────

def scan_folder(root: Path, apply: bool = False) -> list[dict]:
    """
    Scan root (non-recursively) for supported audio files.
    Returns a list of result dicts — one per file.
    """
    results = []

    audio_files = sorted(
        f for f in root.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    total = len(audio_files)
    for idx, fp in enumerate(audio_files, 1):
        print(f"  [{idx:>4}/{total}]  {fp.name}", end="\r", flush=True)

        artist, source = detect_artist(fp)

        row = {
            "file":          fp.name,
            "artist_found":  artist or "",
            "artist_source": source,
            "destination":   "",
            "status":        "",
            "notes":         "",
        }

        if not artist or _is_various(artist):
            row["status"] = "skipped"
            row["notes"]  = "various artists" if (artist and _is_various(artist)) else "no artist detected"
            results.append(row)
            continue

        safe_artist  = sanitise_folder_name(artist)
        dest_dir     = root / safe_artist
        dest_path    = dest_dir / fp.name

        # Collision: if the destination filename already exists, add a counter
        if dest_path.exists() and dest_path.resolve() != fp.resolve():
            stem = fp.stem
            suffix = fp.suffix
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f"{stem} ({counter}){suffix}"
                counter += 1
            row["notes"] = f"renamed to avoid collision: {dest_path.name}"

        row["destination"] = str(dest_dir)
        row["status"]      = "pending" if apply else "would_move"
        results.append(row)

    print()  # clear the \r line
    return results


# ── Reporting ──────────────────────────────────────────────────────────────────

def write_report(results: list[dict], dry_run: bool) -> Path:
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix    = "dry" if dry_run else "applied"
    out_path  = REPORTS_FOLDER / f"{SCRIPT_NAME}_{suffix}_{timestamp}.csv"
    write_csv(results, out_path, FIELDNAMES)
    return out_path


def print_summary(results: list[dict], dry_run: bool, report_path: Path) -> None:
    pending  = [r for r in results if r["status"] in ("pending", "would_move")]
    moved    = [r for r in results if r["status"] == "moved"]
    errors   = [r for r in results if r["status"] == "error"]
    skipped  = [r for r in results if r["status"] == "skipped"]

    print()
    print("=" * 60)
    print(f"  SUMMARY  {'[DRY RUN]' if dry_run else '[APPLIED]'}")
    print("=" * 60)
    if dry_run:
        print(f"  Would move : {len(pending)}")
    else:
        print(f"  Moved      : {len(moved)}")
        if errors:
            print(f"  Errors     : {len(errors)}")
    print(f"  Skipped    : {len(skipped)}")
    print()
    print(f"  Report : {report_path}")
    print("=" * 60)


# ── Apply moves ────────────────────────────────────────────────────────────────

def apply_moves(results: list[dict]) -> list[dict]:
    """Execute moves for all 'pending' rows. Updates status in-place."""
    pending = [r for r in results if r["status"] == "pending"]

    for idx, row in enumerate(pending, 1):
        dest_dir      = Path(row["destination"])   # artist subfolder
        original_name = row["file"]                # just the filename
        dest          = dest_dir / original_name
        # source lives at the unsorted root (one level above the artist subfolder)
        src = dest_dir.parent / original_name

        print(f"  [{idx:>4}/{len(pending)}]  {original_name}  ->  {dest_dir.name}/")

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            row["status"] = "moved"
        except Exception as exc:
            row["status"] = "error"
            row["notes"]  = str(exc)
            print(f"             ! ERROR: {exc}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_sort_by_artist(
    folder: Path,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Sort audio files from a flat folder into artist subfolders.

    Args:
        folder:            Folder containing audio files to sort (scanned non-recursively).
        apply:             False = dry run; True = move files.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: would_move, moved, skipped, errors, results (list of dicts),
              report_path (Path)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    results = scan_folder(folder, apply=apply)

    pending_count = sum(1 for r in results if r["status"] in ("pending", "would_move"))
    skipped_count = sum(1 for r in results if r["status"] == "skipped")

    if not apply:
        report_path = write_report(results, dry_run=True)
        return {"would_move": pending_count, "moved": 0, "skipped": skipped_count,
                "errors": 0, "results": results, "report_path": report_path}

    results = apply_moves(results)
    report_path = write_report(results, dry_run=False)

    moved  = sum(1 for r in results if r["status"] == "moved")
    errors = sum(1 for r in results if r["status"] == "error")

    return {"would_move": 0, "moved": moved, "skipped": skipped_count,
            "errors": errors, "results": results, "report_path": report_path}


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    interactive_options([])

    DRY_RUN = "--apply" not in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    # Resolve root folder
    if _path_flag:
        root = Path(_path_flag.strip('"'))
    else:
        root = pick_folder()
        if not root:
            print("No folder selected. Exiting.")
            sys.exit(0)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    print()
    print("=" * 60)
    print(f"  Sort By Artist  v{VERSION}")
    print("=" * 60)
    print(f"  Folder : {root}")
    print(f"  Mode   : {'DRY RUN - no files will be moved' if DRY_RUN else 'APPLY - files will be moved'}")
    print("=" * 60)
    print()
    print("  Scanning files ...")
    print()

    try:
        result = run_sort_by_artist(root, apply=False)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    results       = result["results"]
    pending_count = result["would_move"]
    skipped_count = result["skipped"]

    print(f"  Found  {len(results)} audio file(s).")
    print(f"  Ready to move  : {pending_count}")
    print(f"  Skipped        : {skipped_count}")

    if DRY_RUN:
        if pending_count:
            print()
            print(f"  {'ARTIST':<40}  FILE")
            print(f"  {'-'*40}  {'-'*30}")
            for r in results:
                if r["status"] == "would_move":
                    dest_folder = Path(r["destination"]).name
                    print(f"  {dest_folder:<40}  {r['file']}")
        print()
        print(f"  {pending_count} file(s) would be moved. Add --apply to execute.")
        print_summary(results, dry_run=True, report_path=result["report_path"])
        return

    if not pending_count:
        print()
        print("  Nothing to move.")
        print_summary(results, dry_run=False, report_path=result["report_path"])
        return

    print()
    confirm = input(f"  Move {pending_count} file(s) into artist subfolders? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.")
        sys.exit(0)

    # Mark as pending and apply
    for r in results:
        if r["status"] == "would_move":
            r["status"] = "pending"

    print()
    results     = apply_moves(results)
    report_path = write_report(results, dry_run=False)
    print_summary(results, dry_run=False, report_path=report_path)


if __name__ == "__main__":
    main()
