"""
Pipeline — Music Tools Batch Processor  v1.1
============================================
Runs the music tools processing pipeline in sequence for a new batch of
downloads. Presents a numbered step menu; launches each selected script in
turn and waits for it to complete.

Pipeline steps:
  1. Build fingerprint cache  (duplicate_finder/build_fp_cache.py)
  2. MusicBrainz lookup       (anjuna_mb_lookup/mb_lookup.py)
  3. Tag files from lookup    (anjuna_mb_lookup/mb_tagger.py)
  4. Sort loose files         (sort_by_artist/sort_by_artist.py)
  5. Sort albums to artists   (sort_albums_to_artists/sort_albums_to_artists.py)

Usage:
    python pipeline.py --pick               # pick batch folder, choose steps
    python pipeline.py --path "C:\\..."     # specify batch folder directly
    python pipeline.py --pick --apply       # launch scripts in apply mode
    python pipeline.py --pick --steps 2 3  # pre-select steps 2 and 3

Default (no --apply): DRY RUN — shows the plan but does not launch any scripts.
With --apply: launches each selected script with the batch folder path pre-filled.
    Each script runs in apply mode. Scripts prompt for confirmation before
    making any changes.

Output:
    Reports saved to: pipeline/reports/pipeline_{dry|applied}_YYYYMMDD_HHMMSS.csv
"""

import sys
from music_tools_common import interactive_options
import subprocess
import csv as csv_mod
from pathlib import Path
from datetime import datetime

def _get_flag_value(flag_name):
    for i, a in enumerate(sys.argv):
        if a == flag_name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
ROOT_DIR    = SCRIPT_DIR.parent
REPORTS_DIR = SCRIPT_DIR / "reports"
PYTHON      = sys.executable

# ── Step definitions ─────────────────────────────────────────────────────────
STEPS = [
    {
        "num":       1,
        "name":      "Build fingerprint cache",
        "script":    ROOT_DIR / "duplicate_finder" / "build_fp_cache.py",
        "desc":      "Pre-computes audio fingerprints for the batch folder.",
        "uses_path": True,
    },
    {
        "num":       2,
        "name":      "MusicBrainz lookup",
        "script":    ROOT_DIR / "anjuna_mb_lookup" / "mb_lookup.py",
        "desc":      "Identifies albums via MusicBrainz. Saves results to a CSV for Step 3.",
        "uses_path": True,
    },
    {
        "num":       3,
        "name":      "Tag files from lookup CSV",
        "script":    ROOT_DIR / "anjuna_mb_lookup" / "mb_tagger.py",
        "desc":      "Writes tags using the MB lookup CSV. You will be asked to pick the report file.",
        "uses_path": False,   # mb_tagger opens its own file picker for the CSV
    },
    {
        "num":       4,
        "name":      "Sort loose files by artist",
        "script":    ROOT_DIR / "sort_by_artist" / "sort_by_artist.py",
        "desc":      "Sorts loose audio files in the batch folder into artist subfolders.",
        "uses_path": True,
    },
    {
        "num":       5,
        "name":      "Sort albums into artist folders",
        "script":    ROOT_DIR / "sort_albums_to_artists" / "sort_albums_to_artists.py",
        "desc":      "Moves tagged album folders into the library's artist folder structure.",
        "uses_path": True,
    },
]


# ── Helpers ──────────────────────────────────────────────────────────────────
def pick_folder():
    import tkinter as tk
    from tkinter import filedialog
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select batch folder to process")
    root_tk.destroy()
    return Path(folder) if folder else None


def print_step_menu():
    print()
    print("  Available steps:")
    for s in STEPS:
        picker_note = "  (picks its own file)" if not s["uses_path"] else ""
        print(f"    {s['num']}. {s['name']}{picker_note}")
        print(f"       {s['desc']}")


def select_steps(steps_preselect=None):
    """Return a sorted list of step numbers chosen by the user."""
    if steps_preselect:
        valid = [s["num"] for s in STEPS]
        chosen = [n for n in steps_preselect if n in valid]
        if chosen:
            return chosen

    print_step_menu()
    print()
    raw = input("  Which steps to run? (e.g. 'all', '1 2 3', '2 3'): ").strip().lower()

    if raw in ("all", "", "a"):
        return [s["num"] for s in STEPS]

    chosen = []
    for token in raw.split():
        if token.isdigit():
            n = int(token)
            if 1 <= n <= len(STEPS):
                chosen.append(n)

    if not chosen:
        print("  No valid steps selected. Exiting.")
        sys.exit(0)

    return sorted(set(chosen))


def build_command(step, batch_path, dry_run=True):
    """Build the subprocess command for a step."""
    cmd = [PYTHON, str(step["script"])]
    if step["uses_path"] and batch_path:
        cmd += ["--path", str(batch_path)]
    if not dry_run:
        cmd.append("--apply")
    return cmd


def run_step(step, batch_path, dry_run=True):
    """Launch a step and wait for it to complete. Returns (status, exit_code)."""
    cmd = build_command(step, batch_path, dry_run)
    print(f"\n  Launching: {' '.join(str(c) for c in cmd)}")
    print()

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print(f"\n  [Step {step['num']} finished — exit code 0]")
        return "completed", 0
    else:
        print(f"\n  [Step {step['num']} finished — exit code {result.returncode}]")
        return "error", result.returncode


def write_report(rows, dry_run=True):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix    = "dry" if dry_run else "applied"
    out_path  = REPORTS_DIR / f"pipeline_{suffix}_{timestamp}.csv"
    fields    = ["step", "name", "script", "status", "exit_code", "command"]
    with open(str(out_path), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv_mod.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  Report saved: {out_path.name}")



# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(
    batch_path,
    steps=None,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Run selected pipeline steps against a batch folder.

    Args:
        batch_path:        Root folder to process.
        steps:             List of step numbers to run (1-5); None = all steps.
        apply:             False = dry run (show plan only); True = launch scripts.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: completed, errors, skipped, rows (list), report_path (Path)

    Raises:
        ValueError: batch_path does not exist or a selected script is missing.
    """
    log        = log_callback or print
    batch_path = Path(batch_path)
    dry_run    = not apply

    if not batch_path.exists() or not batch_path.is_dir():
        raise ValueError(f"Folder not found: {batch_path}")

    chosen_nums  = steps if steps else [s["num"] for s in STEPS]
    chosen_steps = [s for s in STEPS if s["num"] in chosen_nums]

    missing = [s for s in chosen_steps if not s["script"].exists()]
    if missing:
        raise ValueError("Script(s) not found: " + ", ".join(str(s["script"]) for s in missing))

    rows = []
    total = len(chosen_steps)

    if dry_run:
        for s in chosen_steps:
            cmd     = build_command(s, batch_path, dry_run=True)
            cmd_str = " ".join(str(c) for c in cmd)
            log(f"    Step {s['num']}: {cmd_str}")
            rows.append({"step": s["num"], "name": s["name"], "script": str(s["script"]),
                         "status": "planned", "exit_code": "", "command": cmd_str})
        write_report(rows, dry_run=True)
        return {"completed": 0, "errors": 0, "skipped": 0, "rows": rows, "report_path": None}

    for i, step in enumerate(chosen_steps, 1):
        if progress_callback:
            progress_callback(i, total, step["name"])
        status, code = run_step(step, batch_path, dry_run=False)
        cmd_str = " ".join(str(c) for c in build_command(step, batch_path, dry_run=False))
        rows.append({"step": step["num"], "name": step["name"], "script": str(step["script"]),
                     "status": status, "exit_code": code, "command": cmd_str})

    write_report(rows, dry_run=False)
    completed = sum(1 for r in rows if r["status"] == "completed")
    errors    = sum(1 for r in rows if r["status"] == "error")
    skipped   = sum(1 for r in rows if r["status"] == "skipped")
    return {"completed": completed, "errors": errors, "skipped": skipped, "rows": rows,
            "report_path": None}


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    interactive_options([])
    DRY_RUN  = "--apply" not in sys.argv
    PICK_DIR = "--pick"  in sys.argv
    _path_flag = _get_flag_value("--path")
    _steps_preselect = []
    if "--steps" in sys.argv:
        idx = sys.argv.index("--steps")
        for a in sys.argv[idx + 1:]:
            if a.startswith("--"):
                break
            if a.isdigit():
                _steps_preselect.append(int(a))

    print()
    print("  Music Tools Pipeline")
    print("  " + "=" * 56)
    mode = "DRY RUN — scripts will not be launched" if DRY_RUN else "APPLY — scripts will be launched"
    print(f"  Mode   : {mode}")

    # ── Resolve batch folder ────────────────────────────────────────────────
    if _path_flag:
        batch_path = Path(_path_flag.strip('"'))
    else:
        batch_path = pick_folder()
        if not batch_path:
            print("  No folder selected. Exiting.")
            sys.exit(0)

    if not batch_path.exists() or not batch_path.is_dir():
        print(f"  ERROR: Folder not found: {batch_path}")
        sys.exit(1)

    print(f"  Folder : {batch_path}")

    # ── Select steps ────────────────────────────────────────────────────────
    chosen_nums  = select_steps(_steps_preselect)
    chosen_steps = [s for s in STEPS if s["num"] in chosen_nums]

    # Verify all selected scripts exist
    missing = [s for s in chosen_steps if not s["script"].exists()]
    if missing:
        print()
        for s in missing:
            print(f"  ERROR: Script not found: {s['script']}")
        sys.exit(1)

    step_names = ", ".join(f"{s['num']}. {s['name']}" for s in chosen_steps)
    print(f"\n  Selected : {step_names}")

    # ── Dry run: show plan ──────────────────────────────────────────────────
    if DRY_RUN:
        print("\n  DRY RUN — planned commands:\n")
        rows = []
        for s in chosen_steps:
            cmd     = build_command(s, batch_path, DRY_RUN)
            cmd_str = " ".join(str(c) for c in cmd)
            print(f"    Step {s['num']}: {cmd_str}")
            rows.append({
                "step":      s["num"],
                "name":      s["name"],
                "script":    str(s["script"]),
                "status":    "planned",
                "exit_code": "",
                "command":   cmd_str,
            })
        write_report(rows, dry_run=True)
        print("\n  Re-run with --apply to launch the scripts.")
        return

    # ── Apply: confirm then launch ──────────────────────────────────────────
    print()
    confirm = input(f"  Launch {len(chosen_steps)} script(s) in apply mode? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.")
        sys.exit(0)

    rows = []
    for i, step in enumerate(chosen_steps):
        print()
        print(f"  {'─' * 56}")
        print(f"  Step {step['num']} of {len(chosen_steps)}: {step['name']}")
        print(f"  {'─' * 56}")

        status, code = run_step(step, batch_path, DRY_RUN)
        cmd_str = " ".join(str(c) for c in build_command(step, batch_path, DRY_RUN))
        rows.append({
            "step":      step["num"],
            "name":      step["name"],
            "script":    str(step["script"]),
            "status":    status,
            "exit_code": code,
            "command":   cmd_str,
        })

        # Ask to continue (unless this is the last step)
        if i < len(chosen_steps) - 1:
            print()
            cont = input("  Continue to next step? (y/n): ").strip().lower()
            while cont not in ("y", "n"):
                cont = input("  Please enter y or n: ").strip().lower()
            if cont != "y":
                print("  Pipeline stopped.")
                for remaining in chosen_steps[i + 1:]:
                    rows.append({
                        "step":      remaining["num"],
                        "name":      remaining["name"],
                        "script":    str(remaining["script"]),
                        "status":    "skipped",
                        "exit_code": "",
                        "command":   " ".join(str(c) for c in build_command(remaining, batch_path, DRY_RUN)),
                    })
                break

    write_report(rows, dry_run=False)

    completed = sum(1 for r in rows if r["status"] == "completed")
    errors    = sum(1 for r in rows if r["status"] == "error")
    skipped   = sum(1 for r in rows if r["status"] == "skipped")
    print(f"\n  Pipeline complete — {completed} done, {errors} errors, {skipped} skipped.")


if __name__ == "__main__":
    main()
