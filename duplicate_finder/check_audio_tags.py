#!/usr/bin/env python3
"""
check_audio_tags.py \u2014 Scan audio files for missing or invalid AcoustID tags.
v1.7 \u2014 2026-05-25

Checks every audio file in a chosen folder tree for:

  acoustid_id
      Must be a valid UUID in the form  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
      (8-4-4-4-12 lowercase hex digits).
      Files with NO acoustid_id tag are flagged as "missing".
      Values like "acoustid", "acousticid", empty GUIDs, or any non-UUID
      string are flagged as "bad".

  acoustid_fingerprint
      If present, must consist only of base64 or URL-safe base64 characters
      (A-Z a-z 0-9 + / - _ =) and be at least 50 characters long.
      MusicBrainz Picard stores Chromaprint fingerprints in URL-safe base64
      (using - and _ instead of + and /); both variants are accepted.
      Real Chromaprint fingerprints are typically 100-200 characters.

In --apply mode the bad (malformed) tag(s) are deleted from the file so that
MusicBrainz Picard can repopulate them correctly on the next scan.
Missing tags are reported but cannot be auto-fixed \u2014 run Picard on those files.
File contents (audio data) are never modified; only embedded metadata changes.

Flags
-----
  --path "C:\\..."   Specify the scan folder directly on the command line
  --apply            Delete bad tags; default is dry-run (report only)
  --skip-missing     Do not flag files that are simply missing an AcoustID tag
  --include-short    Also flag files shorter than the min-length threshold (default: short tracks skipped)
  --min-length N     Threshold in seconds for short-track filtering (default: 30)
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import mutagen

# -- project root on sys.path so we can import music_tools_common -------------
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from music_tools_common import SUPPORTED_EXTENSIONS, pick_folder, interactive_options
    _COMMON_IMPORTED = True
except ImportError:
    _COMMON_IMPORTED = False
    SUPPORTED_EXTENSIONS = {
        ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus",
        ".wma", ".wav", ".aiff", ".aif", ".ape", ".wv",
    }

    def pick_folder(title: str = "Select folder") -> "Path | None":
        import tkinter as tk
        from tkinter import filedialog
        root_tk = tk.Tk()
        root_tk.withdraw()
        root_tk.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title)
        root_tk.destroy()
        return Path(folder) if folder else None


# -- constants (no side effects on import) -------------------------------------
SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
BASE64_RE  = re.compile(r"^[A-Za-z0-9+/\-_]+=*$")
FP_MIN_LENGTH = 50


# -- validation helpers --------------------------------------------------------
def validate_acoustid_id(value: str, skip_missing: bool) -> tuple[str | None, bool]:
    """
    Return (error_description, is_missing).
    is_missing is True when the tag is absent entirely (vs present but malformed).
    Returns (None, False) if the value is valid.
    """
    if not value:
        if skip_missing:
            return None, False
        return "missing \u2014 run MusicBrainz Picard to tag this file", True
    if not UUID_RE.match(value.strip().lower()):
        return f"not a valid UUID: {value!r}", False
    return None, False


def validate_acoustid_fingerprint(value: str) -> str | None:
    """Return an error description, or None if the value is valid (or absent)."""
    if not value:
        return None
    v = value.strip()
    if len(v) < FP_MIN_LENGTH:
        return f"too short ({len(v)} chars, expected >={FP_MIN_LENGTH})"
    if not BASE64_RE.match(v):
        return "contains invalid characters (not base64)"
    return None


# -- tag reading and writing ---------------------------------------------------
def read_acoustid_tags(path: Path) -> tuple[str, str, float | None, str | None]:
    """
    Read acoustid_id, acoustid_fingerprint, and duration from an audio file.
    Returns (acoustid_id, acoustid_fingerprint, duration_secs, error_message).
    """
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return "", "", None, "mutagen could not parse file"
        aid      = audio.get("acoustid_id",          [""])[0]
        afp      = audio.get("acoustid_fingerprint", [""])[0]
        duration = audio.info.length if hasattr(audio, "info") and audio.info else None
        return aid, afp, duration, None
    except Exception as exc:
        return "", "", None, str(exc)


def clear_bad_tags(path: Path, clear_id: bool, clear_fp: bool) -> str | None:
    """
    Delete the specified AcoustID tag(s) from the file.
    Returns None on success, or an error string if something went wrong.
    Only the tags are modified \u2014 audio data is untouched.
    """
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return "mutagen could not parse file"
        changed = False
        if clear_id and "acoustid_id" in audio:
            del audio["acoustid_id"]
            changed = True
        if clear_fp and "acoustid_fingerprint" in audio:
            del audio["acoustid_fingerprint"]
            changed = True
        if changed:
            audio.save()
        return None
    except Exception as exc:
        return str(exc)


# -- scanning ------------------------------------------------------------------
def scan_folder(root: Path, skip_short: bool = True, min_length_secs: int = 30,
                skip_missing: bool = False,
                progress_callback=None) -> list[dict]:
    """
    Walk root recursively and check every audio file for AcoustID tag problems.
    Returns a list of dicts \u2014 one per file with at least one issue.
    """
    all_files = sorted(
        f for f in root.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    total = len(all_files)
    print(f"  Scanning {total:,} audio file(s) in:")
    print(f"    {root}")
    if skip_short:
        print(f"  Skipping tracks shorter than {min_length_secs}s")
    print()

    BAR_WIDTH = 30

    def _progress_bar(i: int, issues_found: int, skipped: int) -> None:
        pct    = i / total if total else 1
        filled = int(BAR_WIDTH * pct)
        bar    = "\u2588" * filled + "\u2591" * (BAR_WIDTH - filled)
        skip_str = f"  skipped: {skipped}" if skip_short else ""
        print(f"\r  [{bar}] {i:>{len(str(total))}}/{total}  "
              f"({pct*100:5.1f}%)  issues: {issues_found}{skip_str}   ",
              end="", flush=True)

    issues  = []
    skipped = 0

    for i, path in enumerate(all_files, 1):
        _progress_bar(i, len(issues), skipped)

        if progress_callback:
            progress_callback(i, total, path.name)

        aid, afp, duration, read_err = read_acoustid_tags(path)

        if read_err:
            issues.append({
                "path": str(path), "issue": "read_error",
                "bad_id": "", "id_error": "", "missing_id": False,
                "bad_fp": "", "fp_error": "", "error": read_err,
                "clear_id": False, "clear_fp": False, "duration": duration,
            })
            continue

        if skip_short and duration is not None and duration < min_length_secs:
            id_err, is_missing_id = validate_acoustid_id(aid, skip_missing)
            fp_err                = validate_acoustid_fingerprint(afp)
            if is_missing_id and not fp_err:
                skipped += 1
                continue
            if is_missing_id:
                id_err, is_missing_id = None, False

        id_err, is_missing_id = validate_acoustid_id(aid, skip_missing)
        fp_err                = validate_acoustid_fingerprint(afp)

        if id_err or fp_err:
            parts = []
            if id_err:
                parts.append("missing_acoustid_id" if is_missing_id else "bad_acoustid_id")
            if fp_err:
                parts.append("bad_acoustid_fingerprint")
            issues.append({
                "path":       str(path),
                "issue":      " + ".join(parts),
                "bad_id":     aid   if (id_err and not is_missing_id) else "",
                "id_error":   id_err or "",
                "missing_id": is_missing_id,
                "bad_fp":     (afp[:100] + "\u2026") if (fp_err and len(afp) > 100) else (afp if fp_err else ""),
                "fp_error":   fp_err or "",
                "error":      "",
                "clear_id":   bool(id_err and not is_missing_id),
                "clear_fp":   bool(fp_err),
                "duration":   duration,
            })

    print()  # newline after progress bar

    if skip_short and skipped:
        print(f"  Skipped {skipped:,} short track(s) (< {min_length_secs}s) \u2014 missing ID not flagged\n")

    return issues


# -- reporting -----------------------------------------------------------------
def write_report(issues: list[dict], dry_run: bool,
                 reports_folder: Path | None = None) -> Path:
    folder = reports_folder or REPORTS_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "dry" if dry_run else "applied"
    out    = folder / f"check_audio_tags_{suffix}_{ts}.csv"

    fieldnames = [
        "Path", "Duration (s)", "Issue",
        "Bad acoustid_id", "ID Error Detail", "Missing acoustid_id",
        "Bad acoustid_fingerprint", "FP Error Detail", "Read Error", "Action",
    ]

    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in issues:
            if row["issue"] == "read_error":
                action = "could not read"
            elif row.get("missing_id") and not row.get("clear_id") and not row.get("clear_fp"):
                action = "needs Picard tagging"
            elif dry_run:
                action = "skipped (dry run)"
            else:
                parts = []
                if row.get("clear_id") or row.get("clear_fp"):
                    parts.append("bad tags cleared")
                if row.get("missing_id"):
                    parts.append("missing \u2014 needs Picard")
                action = "; ".join(parts) if parts else "no action"

            dur = row.get("duration")
            writer.writerow({
                "Path":                     row["path"],
                "Duration (s)":             f"{dur:.1f}" if dur is not None else "",
                "Issue":                    row["issue"],
                "Bad acoustid_id":          row.get("bad_id",   ""),
                "ID Error Detail":          row.get("id_error", ""),
                "Missing acoustid_id":      "yes" if row.get("missing_id") else "",
                "Bad acoustid_fingerprint": row.get("bad_fp",   ""),
                "FP Error Detail":          row.get("fp_error", ""),
                "Read Error":               row.get("error",    ""),
                "Action":                   action,
            })

    return out


# -- GUI-callable core ---------------------------------------------------------
def run_check_audio_tags(
    root=None,
    apply=False,
    skip_missing=False,
    skip_short=True,
    min_length_secs=30,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    GUI-callable entry point for the AcoustID tag checker.

    Parameters
    ----------
    root : str | Path
        Folder to scan. Required (raises ValueError if None or missing).
    apply : bool
        If True, delete malformed tags. Default: False (dry run).
    skip_missing : bool
        If True, suppress warnings for files with no AcoustID tag.
    skip_short : bool
        If True, skip missing-ID warnings for tracks under min_length_secs.
    min_length_secs : int
        Duration threshold for short-track suppression (default: 30).
    reports_dir : str | Path | None
        Override the reports folder.  Defaults to <script_dir>/reports/.
    progress_callback : callable | None
        Called as progress_callback(current, total, filename).
    log_callback : callable | None
        Called as log_callback(message) — reserved for future use.

    Returns
    -------
    dict: issues (list), counts (dict), report_path (str), reports_dir (str).

    Raises
    ------
    ValueError
        If root is None, does not exist, or is not a directory.
    """
    if root is None:
        raise ValueError("root folder must be specified")
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Folder not found: {root}")

    rdir = Path(reports_dir) if reports_dir else REPORTS_FOLDER

    dry_run = not apply
    issues  = scan_folder(root, skip_short=skip_short,
                          min_length_secs=min_length_secs,
                          skip_missing=skip_missing,
                          progress_callback=progress_callback)

    tag_issues  = [r for r in issues if r["issue"] != "read_error"]
    read_errors = [r for r in issues if r["issue"] == "read_error"]
    bad_tags    = [r for r in tag_issues if r["clear_id"] or r["clear_fp"]]
    missing_only = [r for r in tag_issues
                    if r.get("missing_id") and not r["clear_id"] and not r["clear_fp"]]

    if not dry_run and bad_tags:
        for row in bad_tags:
            err = clear_bad_tags(Path(row["path"]),
                                 clear_id=row["clear_id"],
                                 clear_fp=row["clear_fp"])
            if err:
                row["error"] = err

    report_path = write_report(issues, dry_run, rdir)

    counts = {
        "total_issues": len(issues),
        "tag_issues":   len(tag_issues),
        "read_errors":  len(read_errors),
        "missing_only": len(missing_only),
        "bad_tags":     len(bad_tags),
    }
    return {
        "issues":      issues,
        "counts":      counts,
        "report_path": str(report_path),
        "reports_dir": str(rdir),
    }


# -- main ----------------------------------------------------------------------
def main() -> None:
    interactive_options([
        ("--skip-missing", "Skip missing \u2014 do not flag files with no AcoustID tag"),
    ])

    DRY_RUN      = "--apply"         not in sys.argv
    SKIP_MISSING = "--skip-missing"  in sys.argv
    SKIP_SHORT   = "--include-short" not in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)), None,
    )
    _min_length_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--min-length" and i + 1 < len(sys.argv)), None,
    )
    try:
        min_length_secs = int(_min_length_flag) if _min_length_flag else 30
    except ValueError:
        print(f"ERROR: --min-length must be a whole number of seconds, got: {_min_length_flag!r}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Check Audio Tags \u2014 AcoustID Tag Validator")
    mode_str = "DRY RUN \u2014 no changes will be made" if DRY_RUN else "APPLY \u2014 bad tags will be deleted"
    if SKIP_MISSING:
        mode_str += "  |  missing tags skipped"
    if SKIP_SHORT:
        mode_str += f"  |  short tracks skipped (< {min_length_secs}s)"
    print(f"  Mode : {mode_str}")
    print("=" * 60)
    print()

    if _path_flag:
        root = Path(_path_flag.strip('"'))
    else:
        root = pick_folder("Select folder to scan for AcoustID tag issues")
        if not root:
            print("No folder selected. Exiting.")
            sys.exit(0)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    issues = scan_folder(root, skip_short=SKIP_SHORT,
                         min_length_secs=min_length_secs,
                         skip_missing=SKIP_MISSING)

    tag_issues  = [r for r in issues if r["issue"] != "read_error"]
    read_errors = [r for r in issues if r["issue"] == "read_error"]
    missing_only = [r for r in tag_issues
                    if r.get("missing_id") and not r["clear_id"] and not r["clear_fp"]]
    bad_tags    = [r for r in tag_issues if r["clear_id"] or r["clear_fp"]]
    mixed       = [r for r in tag_issues if r.get("missing_id") and (r["clear_id"] or r["clear_fp"])]

    if not issues:
        print("  No AcoustID tag issues found.")
        out = write_report(issues, DRY_RUN)
        print(f"\n  Report : {out}")
        return

    if tag_issues:
        missing_count = sum(1 for r in tag_issues if r.get("missing_id"))
        bad_id_count  = sum(1 for r in tag_issues if r["clear_id"])
        bad_fp_count  = sum(1 for r in tag_issues if r["clear_fp"])
        bad_both      = sum(1 for r in tag_issues if r["clear_id"] and r["clear_fp"])

        print(f"  Found {len(tag_issues)} file(s) with AcoustID tag issues:")
        if missing_count:  print(f"    Missing acoustid_id        : {missing_count}  (need Picard tagging)")
        if bad_id_count:   print(f"    Bad acoustid_id            : {bad_id_count}  (malformed \u2014 will clear)")
        if bad_fp_count:   print(f"    Bad acoustid_fingerprint   : {bad_fp_count}  (malformed \u2014 will clear)")
        if bad_both:       print(f"    Both ID and FP bad         : {bad_both}")
        print()

        for row in tag_issues:
            label   = "[MISSING]" if (row.get("missing_id") and not row["clear_id"]) else "[BAD TAG]"
            dur     = row.get("duration")
            dur_str = f"  ({dur:.0f}s)" if dur is not None else ""
            print(f"  {label} {row['path']}{dur_str}")
            if row.get("id_error"):  print(f"    acoustid_id          -> {row['id_error']}")
            if row.get("fp_error"):  print(f"    acoustid_fingerprint -> {row['fp_error']}")

    if read_errors:
        print()
        print(f"  {len(read_errors)} file(s) could not be read:")
        for row in read_errors:
            print(f"  [READ ERROR] {row['path']}")
            print(f"    {row['error']}")

    files_to_clear = bad_tags + mixed
    if not DRY_RUN and files_to_clear:
        print()
        print(f"  This will delete the malformed tag(s) from {len(files_to_clear)} file(s).")
        print("  Audio data is not modified \u2014 only the embedded AcoustID metadata.")
        print("  Run MusicBrainz Picard afterward to repopulate correct tags.")
        if missing_only:
            print(f"  Note: {len(missing_only)} file(s) with missing tags are NOT changed \u2014 run Picard on those.")
        print()
        confirm = input(f"  Delete bad tags from {len(files_to_clear)} file(s)? (y/n): ").strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted \u2014 no changes made.")
            out = write_report(issues, dry_run=True)
            print(f"\n  Report : {out}")
            sys.exit(0)

        print()
        cleared = 0
        failed  = 0
        for row in files_to_clear:
            err = clear_bad_tags(Path(row["path"]),
                                 clear_id=row["clear_id"],
                                 clear_fp=row["clear_fp"])
            if err:
                row["error"] = err
                failed += 1
            else:
                cleared += 1

        print(f"\n  {'='*40}")
        print(f"  Tags cleared      : {cleared}")
        if missing_only:
            print(f"  Needs Picard      : {len(missing_only)}")
        print(f"  Errors            : {failed}")
        print(f"  {'='*40}\n")

    elif not DRY_RUN and missing_only:
        print()
        print("  No bad tags to clear.")
        print(f"  {len(missing_only)} file(s) need MusicBrainz Picard tagging \u2014 no automatic fix.")

    out = write_report(issues, DRY_RUN)
    print(f"\n  Report : {out}")


if __name__ == "__main__":
    main()
