"""
Music Tools Setup  v1.1
=======================
Interactive first-run wizard. Configures music_config.json for the
Music Duplicate Finder and related tools.

Run once after cloning the repository to set your folder paths and
preferences. Safe to re-run at any time to update settings — press
Enter at any prompt to keep the existing value.

Usage:
    python setup_music_tools.py            # guided wizard (loads existing config)
    python setup_music_tools.py --reset    # ignore existing config, start from defaults
"""

import sys
import json
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "music_config.json"

sys.path.insert(0, str(SCRIPT_DIR))
from music_tools_common import pick_folder

RESET = "--reset" in sys.argv


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULTS = {
    "folders": {
        "organized":      "",
        "unsorted":       "",
        "duplicates":     "",
        "better_quality": "",
    },
    "matching": {
        "mode":                               "4",
        "fuzzy_enabled":                      True,
        "fuzzy_threshold":                    88,
        "use_duration":                       True,
        "duration_tolerance_seconds":         2,
        "exact_match_size_tolerance_percent": 3.0,
    },
    "performance": {
        "max_threads":   0,
        "cache_enabled": True,
    },
    "resume": {
        "enabled":     True,
        "resume_file": "music_resume.json",
    },
    "output": {
        "log_folder": "",
    },
    "acoustid": {
        "enabled":              True,
        "fpcalc_path":          "",
        "similarity_threshold": 85,
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def divider(label=""):
    if label:
        line = "── %s " % label
        print("\n%s%s" % (line, "─" * max(0, 78 - len(line))))
    else:
        print("\n" + "─" * 80)


def ask_folder(label, current, description="", allow_create=False):
    """
    Prompt for a folder path via picker dialog or typed input.
    Press Enter to keep current value, P to open a folder picker.
    Offers to create the folder if it doesn't exist (when allow_create=True).
    Returns path as a string.
    """
    print()
    print("  %s" % label)
    if description:
        print("  %s" % description)
    if current:
        print("  Current : %s" % current)
    else:
        print("  Current : (not set)")

    while True:
        if current:
            raw = input("  Enter to keep / P to pick / type a path: ").strip()
        else:
            raw = input("  P to pick a folder / type a path: ").strip()

        if not raw and current:
            return current

        if raw.upper() == "P" or (not raw and not current):
            chosen = pick_folder(title=label)
            if not chosen:
                print("  No folder selected.")
                if current:
                    return current
                continue
            path_str = str(chosen)
        else:
            path_str = raw.strip('"').strip("'")

        p = Path(path_str)

        if p.is_dir():
            print("  ✓  %s" % path_str)
            return path_str

        if p.exists():
            print("  ! That path exists but is not a folder — try again.")
            continue

        # Path doesn't exist
        if allow_create:
            yn = input("  Folder doesn't exist. Create it? (y/n): ").strip().lower()
            if yn == "y":
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    print("  ✓  Created: %s" % path_str)
                    return path_str
                except Exception as e:
                    print("  ! Could not create folder: %s" % e)
                    continue
            else:
                print("  Skipped creation — try a different path.")
                continue
        else:
            print("  ! Folder not found: %s" % path_str)
            yn = input("  Use this path anyway? (y/n): ").strip().lower()
            if yn == "y":
                return path_str
            continue


def ask_fpcalc(current):
    """
    Prompt for fpcalc.exe path via file picker or typed input.
    Returns path as a string (may be empty if not set).
    """
    print()
    print("  fpcalc.exe path — the fingerprint calculator tool")
    print("  Download free from: https://acoustid.org/chromaprint")
    if current:
        print("  Current : %s" % current)
    else:
        print("  Current : (not set)")

    while True:
        if current:
            raw = input("  Enter to keep / P to pick fpcalc.exe / type a path: ").strip()
        else:
            raw = input("  P to pick fpcalc.exe / type a path / Enter to skip: ").strip()

        if not raw:
            return current  # keep (even if empty)

        if raw.upper() == "P":
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                chosen = filedialog.askopenfilename(
                    title="Select fpcalc.exe",
                    filetypes=[
                        ("fpcalc executable", "fpcalc.exe"),
                        ("Executable files", "*.exe"),
                        ("All files", "*.*"),
                    ],
                )
                root.destroy()
                if chosen:
                    print("  ✓  %s" % chosen)
                    return chosen
                else:
                    print("  No file selected.")
                    if current:
                        return current
                    continue
            except Exception as e:
                print("  ! Could not open picker: %s" % e)
                continue

        path_str = raw.strip('"').strip("'")
        p = Path(path_str)
        if p.is_file():
            print("  ✓  %s" % path_str)
            return path_str
        else:
            print("  ! File not found: %s" % path_str)
            yn = input("  Use this path anyway? (y/n): ").strip().lower()
            if yn == "y":
                return path_str
            continue


def ask_yn(label, current, description=""):
    """Prompt for a yes/no setting. Returns bool."""
    print()
    print("  %s" % label)
    if description:
        print("  %s" % description)
    current_str = "Y" if current else "N"
    while True:
        raw = input("  Current [%s] — Y/N or Enter to keep: " % current_str).strip().upper()
        if not raw:
            return current
        if raw in ("Y", "YES"):
            return True
        if raw in ("N", "NO"):
            return False
        print("  Please enter Y or N.")


def ask_int(label, current, description="", min_val=None, max_val=None):
    """Prompt for an integer. Returns int."""
    print()
    print("  %s" % label)
    if description:
        print("  %s" % description)
    while True:
        raw = input("  Current [%s] — enter a number or press Enter to keep: " % current).strip()
        if not raw:
            return current
        try:
            val = int(raw)
            if min_val is not None and val < min_val:
                print("  Minimum is %d." % min_val)
                continue
            if max_val is not None and val > max_val:
                print("  Maximum is %d." % max_val)
                continue
            return val
        except ValueError:
            print("  Please enter a whole number.")


def ask_float(label, current, description="", min_val=None, max_val=None):
    """Prompt for a float. Returns float."""
    print()
    print("  %s" % label)
    if description:
        print("  %s" % description)
    while True:
        raw = input("  Current [%s] — enter a number or press Enter to keep: " % current).strip()
        if not raw:
            return current
        try:
            val = float(raw)
            if min_val is not None and val < min_val:
                print("  Minimum is %s." % min_val)
                continue
            if max_val is not None and val > max_val:
                print("  Maximum is %s." % max_val)
                continue
            return val
        except ValueError:
            print("  Please enter a number (e.g. 3.0).")


def ask_choice(label, current, choices, descriptions):
    """Prompt for a choice from a fixed set. Returns chosen value as string."""
    print()
    print("  %s" % label)
    for k, desc in zip(choices, descriptions):
        marker = " ←" if k == current else ""
        print("    %s = %s%s" % (k, desc, marker))
    while True:
        raw = input("  Current [%s] — enter %s or press Enter to keep: " % (
            current, "/".join(choices))).strip()
        if not raw:
            return current
        if raw in choices:
            return raw
        print("  Please enter one of: %s" % ", ".join(choices))


def load_existing():
    """
    Load the existing config and merge with defaults (handles new keys added
    in later versions). Returns a plain dict per section, no _comment keys.
    """
    if not CONFIG_PATH.exists() or RESET:
        return {k: v.copy() for k, v in DEFAULTS.items()}

    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        merged = {k: v.copy() for k, v in DEFAULTS.items()}
        for section, vals in raw.items():
            if section.startswith("_"):
                continue
            if section in merged and isinstance(vals, dict):
                for key, val in vals.items():
                    if not key.startswith("_") and key in merged[section]:
                        merged[section][key] = val
        return merged
    except Exception as e:
        print("\n  WARNING: Could not read existing config (%s). Starting from defaults." % e)
        return {k: v.copy() for k, v in DEFAULTS.items()}


def build_config(cfg):
    """
    Reconstruct the full music_config.json structure including all _comment
    keys, ready to serialise to disk.
    """
    return {
        "_comment": "Music Duplicate Finder - Configuration File",

        "folders": {
            "_comment":       "organized: your main sorted music library",
            "organized":      cfg["folders"]["organized"],
            "_comment2":      "unsorted: folder of new downloads to check against the library",
            "unsorted":       cfg["folders"]["unsorted"],
            "_comment3":      "duplicates: confirmed duplicates are moved here for review",
            "duplicates":     cfg["folders"]["duplicates"],
            "_comment4":      "better_quality: unsorted files that are higher bitrate than your library copy",
            "better_quality": cfg["folders"]["better_quality"],
        },

        "matching": {
            "_comment":                           "mode: default match mode — 1=filename, 2=metadata, 3=either, 4=both (recommended)",
            "mode":                               cfg["matching"]["mode"],
            "_comment2":                          "fuzzy_enabled: use fuzzy matching for artist/title/album tags",
            "fuzzy_enabled":                      cfg["matching"]["fuzzy_enabled"],
            "_comment3":                          "fuzzy_threshold: 0-100. How similar tags must be. 88 recommended.",
            "fuzzy_threshold":                    cfg["matching"]["fuzzy_threshold"],
            "_comment4":                          "use_duration: check track duration when matching",
            "use_duration":                       cfg["matching"]["use_duration"],
            "_comment5":                          "duration_tolerance_seconds: max duration difference to still count as a match",
            "duration_tolerance_seconds":         cfg["matching"]["duration_tolerance_seconds"],
            "_comment6":                          "exact_match_size_tolerance_percent: file size difference allowed for auto-move",
            "exact_match_size_tolerance_percent": cfg["matching"]["exact_match_size_tolerance_percent"],
        },

        "performance": {
            "_comment":      "max_threads: parallel threads for scanning. 0 = auto-detect",
            "max_threads":   cfg["performance"]["max_threads"],
            "_comment2":     "cache_enabled: cache organized library metadata between runs (much faster)",
            "cache_enabled": cfg["performance"]["cache_enabled"],
            "_comment3":     "cache_file: metadata + fingerprint cache is now a shared SQLite database",
            "_cache_note":   "music_cache.db lives in the project root (next to music_tools_common.py). No path config needed — all scripts find it automatically via DB_PATH in music_tools_common.",
        },

        "resume": {
            "_comment":    "enabled: allow resuming an interrupted run",
            "enabled":     cfg["resume"]["enabled"],
            "_comment2":   "resume_file: tracks which files have already been processed",
            "resume_file": cfg["resume"]["resume_file"],
        },

        "output": {
            "_comment":   "log_folder: where reports and logs are saved. Leave empty to save in duplicate_finder/reports/ (recommended).",
            "log_folder": cfg["output"]["log_folder"],
        },

        "acoustid": {
            "_comment":             "enabled: offer audio fingerprint matching after the main scan",
            "enabled":              cfg["acoustid"]["enabled"],
            "_comment2":            "fpcalc_path: full path to fpcalc.exe",
            "fpcalc_path":          cfg["acoustid"]["fpcalc_path"],
            "_comment3":            "similarity_threshold: 0-100. How similar fingerprints must be.",
            "similarity_threshold": cfg["acoustid"]["similarity_threshold"],
            "_comment4":            "fp_cache_file: fingerprint cache is now stored in music_cache.db (fp_cache table)",
            "_fp_cache_note":       "No separate file needed. The fp_cache table in music_cache.db holds all fingerprints.",
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 80)
    print("  Music Tools Setup  v1.1")
    print("=" * 80)
    print("  Configures music_config.json for the Music Duplicate Finder.")
    print()
    print("  How it works:")
    print("    The Duplicate Finder compares a folder of new downloads against your")
    print("    organised music library. Files that already exist in your library are")
    print("    moved to a Duplicates folder for safe review. Files that are higher")
    print("    quality than your library copy go to a Better Quality folder. Nothing")
    print("    is ever deleted automatically — you stay in control at every step.")
    print()
    print("  Press Enter at any prompt to keep the current value shown in [brackets].")
    print("=" * 80)

    if CONFIG_PATH.exists() and not RESET:
        print("\n  Found existing config at:")
        print("  %s" % CONFIG_PATH)
        print("  Loading current settings. (Run with --reset to start from defaults.)")
    elif RESET:
        print("\n  --reset: starting from built-in defaults.")
    else:
        print("\n  No existing config found — starting fresh.")

    cfg = load_existing()

    # ── SECTION 1: Folders ────────────────────────────────────────────────────
    divider("SECTION 1: Folders")
    print("  The four folders the Duplicate Finder works with.")
    print("  Press P at any prompt to open a folder picker dialog.")

    cfg["folders"]["organized"] = ask_folder(
        "1/4  Organized library — your main sorted music collection",
        cfg["folders"]["organized"],
        description="  The reference point. The tool scans this to build its index but never"
                    "\n  modifies anything in it — your library is always read-only.",
    )

    cfg["folders"]["unsorted"] = ask_folder(
        "2/4  Unsorted / downloads folder — new files to check against the library",
        cfg["folders"]["unsorted"],
        description="  Files here are what get moved — never files in your organised library."
                    "\n  This is your default comparison folder; you can also override it at"
                    "\n  runtime without changing this config (using the Pick Source launcher).",
    )

    cfg["folders"]["duplicates"] = ask_folder(
        "3/4  Duplicates folder — confirmed duplicates are moved here for review",
        cfg["folders"]["duplicates"],
        description="  Files are moved here (not deleted) so you can check them before"
                    "\n  permanently removing anything. Can be an empty folder you create now.",
        allow_create=True,
    )

    cfg["folders"]["better_quality"] = ask_folder(
        "4/4  Better quality folder — higher-bitrate copies are moved here",
        cfg["folders"]["better_quality"],
        description="  When a file in your downloads is a higher bitrate than your library copy,"
                    "\n  it lands here for review. You may want to replace your library copy with it.",
        allow_create=True,
    )

    # ── SECTION 2: Matching ───────────────────────────────────────────────────
    divider("SECTION 2: Matching Settings")
    print("  Controls how files are identified as duplicates of each other.")
    print("  The defaults work well for most libraries — read each description")
    print("  before changing anything.")

    cfg["matching"]["mode"] = ask_choice(
        "1/6  Match mode",
        cfg["matching"]["mode"],
        choices=["1", "2", "3", "4"],
        descriptions=[
            "filename only",
            "metadata only (artist, title, album tags)",
            "either — match if filename OR metadata match",
            "both — filename AND metadata must both match (recommended)",
        ],
    )

    cfg["matching"]["fuzzy_enabled"] = ask_yn(
        "2/6  Fuzzy matching — tolerate small differences in artist/title/album tags?",
        cfg["matching"]["fuzzy_enabled"],
        description='  e.g. "Above & Beyond" vs "Above and Beyond" would still match',
    )

    if cfg["matching"]["fuzzy_enabled"]:
        cfg["matching"]["fuzzy_threshold"] = ask_int(
            "3/6  Fuzzy threshold — how similar tags must be (0–100, 88 recommended)",
            cfg["matching"]["fuzzy_threshold"],
            description="  Higher = stricter (fewer matches). Lower = more lenient (more matches,"
                        "\n  but higher chance of false positives). 88 comfortably handles common"
                        "\n  variations like '&' vs 'and', missing accents, or minor spacing"
                        "\n  differences, without pairing tracks that are genuinely different songs.",
            min_val=50, max_val=100,
        )
    else:
        print("\n  3/6  Fuzzy threshold — skipped (fuzzy matching disabled)")

    cfg["matching"]["use_duration"] = ask_yn(
        "4/6  Duration check — compare track duration when matching?",
        cfg["matching"]["use_duration"],
        description="  Reduces false positives (e.g. same title, different edit length)",
    )

    if cfg["matching"]["use_duration"]:
        cfg["matching"]["duration_tolerance_seconds"] = ask_int(
            "5/6  Duration tolerance — max difference in seconds (2 recommended)",
            cfg["matching"]["duration_tolerance_seconds"],
            description="  A radio edit and an album version of the same track can share the same"
                        "\n  title and artist tags but have different lengths. 2 seconds is tight"
                        "\n  enough to catch the same file re-encoded or re-tagged, while keeping"
                        "\n  genuine alternate versions separate. Raise to 5 if you're getting too"
                        "\n  many missed matches; lower to 1 for stricter control.",
            min_val=0, max_val=30,
        )
    else:
        print("\n  5/6  Duration tolerance — skipped (duration check disabled)")

    cfg["matching"]["exact_match_size_tolerance_percent"] = ask_float(
        "6/6  File size tolerance — % size difference allowed for exact-match auto-move (3.0 recommended)",
        cfg["matching"]["exact_match_size_tolerance_percent"],
        description="  Two copies of the exact same audio file can have slightly different sizes"
                    "\n  if one has more embedded cover art or extra tags. 3% covers this gap safely."
                    "\n  Going above 5% risks auto-moving files that are actually a different"
                    "\n  encode or bitrate — keep it low unless you're seeing missed exact matches.",
        min_val=0.0, max_val=20.0,
    )

    # ── SECTION 3: Performance ────────────────────────────────────────────────
    divider("SECTION 3: Performance")

    cfg["performance"]["max_threads"] = ask_int(
        "  Parallel scan threads (0 = auto-detect, recommended)",
        cfg["performance"]["max_threads"],
        description="  0 lets the script decide based on your CPU core count — the right choice"
                    "\n  for most machines. Set a fixed number (e.g. 4) if you want to cap CPU"
                    "\n  usage while the scan runs in the background. Higher values scan faster"
                    "\n  but will noticeably compete with other apps on slower machines.",
        min_val=0, max_val=64,
    )

    # ── SECTION 4: AcoustID Fingerprinting ───────────────────────────────────
    divider("SECTION 4: AcoustID Fingerprinting")
    print("  Tag matching alone can miss duplicates that have been re-tagged, renamed,")
    print("  or re-encoded. Fingerprinting analyses the actual audio content — two files")
    print("  that sound identical will match even if all their tags are completely different.")
    print()
    print("  The trade-off: the first run requires building a fingerprint cache of your")
    print("  library (typically 30–60 minutes for a large collection). After that, only")
    print("  new files are fingerprinted, so subsequent runs are fast.")
    print()
    print("  Requires fpcalc.exe — free download from https://acoustid.org/chromaprint")

    cfg["acoustid"]["enabled"] = ask_yn(
        "1/3  Enable AcoustID fingerprint matching?",
        cfg["acoustid"]["enabled"],
        description="  Recommended if your library has files from multiple sources or rips"
                    "\n  that may have inconsistent tags. Can be disabled to keep scans fast.",
    )

    if cfg["acoustid"]["enabled"]:
        cfg["acoustid"]["fpcalc_path"] = ask_fpcalc(cfg["acoustid"]["fpcalc_path"])

        # Validate — warn but don't block
        fp = cfg["acoustid"]["fpcalc_path"]
        if fp and not Path(fp).is_file():
            print("  ! fpcalc.exe not found at that path.")
            print("    You can update it later in music_config.json (project root)")

        cfg["acoustid"]["similarity_threshold"] = ask_int(
            "3/3  Fingerprint similarity threshold (0–100, 85 recommended)",
            cfg["acoustid"]["similarity_threshold"],
            description="  How closely two audio fingerprints must match to count as the same track."
                        "\n  85 is a reliable balance: it catches re-encodes and minor edits but"
                        "\n  won't pair genuinely different tracks. Below 75 risks false positives;"
                        "\n  above 95 may miss real duplicates that were re-encoded at a different"
                        "\n  bitrate.",
            min_val=50, max_val=100,
        )
    else:
        print("\n  2/3  fpcalc path — skipped (fingerprinting disabled)")
        print("  3/3  Similarity threshold — skipped (fingerprinting disabled)")

    # ── SECTION 5: Resume ─────────────────────────────────────────────────────
    divider("SECTION 5: Resume")

    cfg["resume"]["enabled"] = ask_yn(
        "  Allow resuming an interrupted scan?",
        cfg["resume"]["enabled"],
        description="  Saves progress so a crash or interruption can be continued without"
                    "\n  re-scanning from the beginning. Recommended for large libraries.",
    )

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    divider("SUMMARY")
    print("  The following will be written to:")
    print("  %s" % CONFIG_PATH)
    print()

    print("  Folders:")
    print("    Organized    : %s" % (cfg["folders"]["organized"]      or "(not set)"))
    print("    Unsorted     : %s" % (cfg["folders"]["unsorted"]       or "(not set)"))
    print("    Duplicates   : %s" % (cfg["folders"]["duplicates"]     or "(not set)"))
    print("    Better qual. : %s" % (cfg["folders"]["better_quality"] or "(not set)"))

    print()
    print("  Matching:")
    print("    Mode         : %s" % cfg["matching"]["mode"])
    fuzzy_str = ("Enabled (threshold: %d)" % cfg["matching"]["fuzzy_threshold"]
                 if cfg["matching"]["fuzzy_enabled"] else "Disabled")
    print("    Fuzzy        : %s" % fuzzy_str)
    dur_str = ("Enabled (tolerance: %ds)" % cfg["matching"]["duration_tolerance_seconds"]
               if cfg["matching"]["use_duration"] else "Disabled")
    print("    Duration     : %s" % dur_str)
    print("    Size tol.    : %.1f%%" % cfg["matching"]["exact_match_size_tolerance_percent"])

    print()
    print("  Performance:")
    threads = cfg["performance"]["max_threads"]
    print("    Threads      : %s" % ("Auto-detect" if threads == 0 else threads))

    print()
    print("  AcoustID:")
    if cfg["acoustid"]["enabled"]:
        print("    Enabled      : Yes")
        print("    fpcalc       : %s" % (cfg["acoustid"]["fpcalc_path"] or "(not set)"))
        print("    Similarity   : %d" % cfg["acoustid"]["similarity_threshold"])
    else:
        print("    Enabled      : No")

    print()
    print("  Resume        : %s" % ("Enabled" if cfg["resume"]["enabled"] else "Disabled"))

    # ── CONFIRM & WRITE ───────────────────────────────────────────────────────
    print()
    confirm = input("  Write config? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()

    if confirm != "y":
        print()
        print("  Aborted — no changes made.")
        sys.exit(0)

    full_config = build_config(cfg)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(full_config, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 80)
    print("  Setup complete!")
    print("  Config saved to: %s" % CONFIG_PATH)
    print()
    print("  Next steps:")
    print("    1. Build the fingerprint cache :  duplicate_finder\\Run - Build FP Cache (Incremental).cmd")
    print("    2. Run the Duplicate Finder    :  duplicate_finder\\Run - Find Duplicates (Dry Run).cmd")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
