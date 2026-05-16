---
name: music-tools-project-skill
description: >
  Coding standards and conventions for Shrutesh's music library tools project
  (C:\Users\neo_s\Projects\music tools\). Load this skill before writing or
  touching ANY code in this project — new scripts, bug fixes, adding flags,
  updating .cmd files, writing README or CHANGELOG, or reviewing whether a script
  follows project standards. If the task involves music library automation, file
  renaming, duplicate finding, playlist repair, folder scanning, CD track sorting,
  integrity checking, or anything else in the music tools folder, this skill MUST
  be loaded first. Do not write a single line of Python or batch script for this
  project without consulting it.
---

# Music Tools — Project Coding Standards

These are the non-negotiable conventions for every script in this project. They exist
because Shrutesh is not a developer — scripts must be safe, transparent, and recoverable
without him needing to read or edit code.

---

## 1. Dry-run by default

Every script that moves, renames, deletes, or modifies files must default to a **dry run**.
Nothing happens unless `--apply` is passed explicitly. This prevents accidents when
double-clicking a shortcut.

```python
DRY_RUN = "--apply" not in sys.argv
```

Always print the mode clearly at the top of every run:

```
Mode : DRY RUN — no changes will be made
```

---

## 2. Folder/path selection — use `--pick`, never hardcode

Scripts must never hardcode absolute paths. Use a `--pick` flag that opens a native
Windows folder dialog via tkinter. Also support `--path "C:\..."` for scripted use.
If neither is provided, print a clear error explaining how to use them — don't silently
fall back to a hardcoded path.

```python
PICK_DIR = "--pick" in sys.argv

def pick_folder() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select folder to scan")
    root_tk.destroy()
    return Path(folder) if folder else None

# In main:
if PICK_DIR:
    root = pick_folder()
    if not root:
        print("No folder selected. Exiting.")
        sys.exit(0)
elif _path_flag:
    root = Path(_path_flag.strip('"'))
else:
    print("ERROR: No folder specified. Use --pick or --path.")
    sys.exit(1)
```

---

## 3. Validate paths before proceeding

Always check that the input path exists and is a directory before doing any work:

```python
if not root.exists() or not root.is_dir():
    print(f"ERROR: Folder not found: {root}")
    sys.exit(1)
```

---

## 4. Use `shutil.move`, never `Path.rename` or `os.rename`

`Path.rename()` fails silently across drives (e.g., C: to E:). `shutil.move` handles
cross-device moves correctly and is the standard for this project.

```python
import shutil
shutil.move(str(old_path), str(new_path))
```

---

## 5. Confirmation prompt before any destructive action

In `--apply` mode, always show the full list of planned changes and ask for explicit
confirmation before touching anything. Never act first and ask later.

```python
confirm = input(f"  Rename {len(candidates)} folder(s)? (y/n): ").strip().lower()
while confirm not in ("y", "n"):
    confirm = input("  Please enter y or n: ").strip().lower()
if confirm != "y":
    print("  Aborted.")
    sys.exit(0)
```

---

## 6. Reports saved to `<script_folder>/reports/`

Every run (dry and live) must save a timestamped CSV report. The reports folder lives
**next to the script**, never at an absolute path.

```python
SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# In write_report():
REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
suffix    = "dry" if dry_run else "applied"
out_path  = REPORTS_FOLDER / f"{script_name}_{suffix}_{timestamp}.csv"
```

---

## 7. `.cmd` launcher files — two per script, no hardcoded paths

Every script ships with exactly two `.cmd` files:

**`Run - Script Name (Dry Run).cmd`**
```batch
@echo off
cd /d "%~dp0"
python script_name.py --pick
pause
```

**`Run - Script Name (Apply).cmd`**
```batch
@echo off
cd /d "%~dp0"
python script_name.py --pick --apply
pause
```

Rules:
- `cd /d "%~dp0"` ensures the script runs from its own folder (so relative paths work)
- `--pick` in both — never a hardcoded path in a `.cmd` file
- `pause` at the end so the window stays open after the run

---

## 8. README.md and CHANGELOG.md

Every script folder has a `README.md` and a `CHANGELOG.md`. **Update both whenever you
change a script.**

**README.md** should cover:
- What the script does (one paragraph)
- Usage (the flags: `--pick`, `--apply`, `--path`)
- Output (what the report contains)
- Requirements (Python packages, if any)

**CHANGELOG.md** format:
```markdown
## v1.X — YYYY-MM-DD

### Added / Fixed / Changed
- Description of change
```

Always increment the version number in both the script docstring and the changelog.

---

## 9. argparse-style flags (manual, not the `argparse` library)

The project uses manual flag parsing with `sys.argv` rather than the `argparse` library.
This keeps scripts runnable without pip-installing anything. Follow the existing pattern:

```python
DRY_RUN  = "--apply" not in sys.argv
PICK_DIR = "--pick"  in sys.argv

_path_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--path" and i + 1 < len(sys.argv)),
    None,
)
```

---

## 10. Project folder layout

```
C:\Users\neo_s\Projects\music tools\
├── <script_name>/
│   ├── <script_name>.py
│   ├── Run - <Script Name> (Dry Run).cmd
│   ├── Run - <Script Name> (Apply).cmd
│   ├── README.md
│   ├── CHANGELOG.md
│   └── reports/          ← auto-created on first run
```

Music library: `E:\Music`
New downloads staging: `C:\Users\neo_s\Downloads\To Move\`

---

## 11. HTML report viewers

Several tools include an HTML viewer file (e.g., `music_report_viewer.html`,
`scan_report_viewer.html`) that let Shrutesh browse CSV reports visually in a browser.
When building or modifying these viewers, follow these principles:

- **All states covered**: empty state (no report loaded), normal, and error
- **Keyboard works**: table rows, buttons, and filters must all be operable by keyboard
- **Accessible labels**: every icon-only button needs an `aria-label`
- **No external dependencies**: viewers must work offline — no CDN calls, everything inline
- **Consistent look**: use the same colour palette, font stack, and table style as other
  viewers in the project to keep the UI family coherent

Reference: [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines)
is a useful checklist for interactions, layout, accessibility, and form behaviour when
doing more involved viewer work.

---

## Quick checklist for any new or modified script

Before considering a script done, verify:

- [ ] Dry-run is the default (`--apply` required)
- [ ] `--pick` opens a folder dialog; `--path` also accepted
- [ ] Path existence validated before proceeding
- [ ] `shutil.move` used (not `Path.rename` or `os.rename`)
- [ ] Confirmation prompt shown before any destructive action in `--apply` mode
- [ ] Reports saved to `<script_folder>/reports/` with timestamp
- [ ] Two `.cmd` files present (dry run and apply), both using `--pick`
- [ ] README.md updated
- [ ] CHANGELOG.md updated with new version and date
