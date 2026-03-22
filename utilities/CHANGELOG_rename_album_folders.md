# Changelog — rename_album_folders.py

All notable changes to the Album Folder Renamer are documented here.

---

## [2.2] - 2026-03-19

### Fixed
- **Multi-CD detection not working** — the CD parent folder was not being detected in practice because `rglob` was visiting CD subfolders (CD1, CD2) before their parent. This caused the script to add each CD subfolder as an individual rename candidate, producing collision errors (three folders all trying to rename to "Best of Bonkers"). Fixed by sorting all directories by depth before processing, ensuring parents are always evaluated before their children. The parent is now correctly identified and renamed, and the CD subfolders are left untouched.

---

## [2.1] - 2026-03-15

### Added
- **Multi-CD album support** — folders that contain only CD/Disc/Disk subfolders (e.g. `CD1`, `CD 2`, `Disc1`) are now detected as multi-CD albums. The **parent folder** is renamed to match the album tag, and the individual CD subfolders are left untouched. Previously the script would try to rename the CD subfolders themselves and ignore the parent entirely.
- **Multi-CD column in report** — the CSV report now includes a `Multi-CD` column (`Yes`/`No`) so you can see at a glance which folders were handled as multi-disc albums.
- **Multi-CD label in preview** — the console dry-run preview shows `(multi-CD: N discs)` next to any folder detected as a multi-CD parent.

### Changed
- `find_album_folders()` now performs a two-pass check per folder: first looking for CD subfolders (multi-CD structure), then falling back to direct music file detection (normal structure). CD subfolders that belong to a detected parent are excluded from the candidate list to prevent double-processing.

---

## [2.0] - 2026-03-14

### Added
- **Reports saved after every run** — both dry runs and live runs now save a timestamped CSV to the reports folder. Columns: Relative Path, Current Name, New Name, Album Tag, Status, Files.
- **Track titles in conflict prompt** — when files in a folder disagree on the album tag, each option now shows up to 4 track titles sorted by track number alongside the count. Makes it much easier to identify the correct album without having to open the folder.
- **`--filter` flag** — skips folders whose current name already matches their album tag. Useful on subsequent runs where most folders are already correct, significantly reducing scan time on large libraries.
- **`--depth N` flag** — restricts the scan to folders exactly N levels deep relative to the root. Use `--depth 2` for a classic Artist/Album structure to avoid touching artist-level or other structural folders unintentionally.
- **Cross-folder collision detection** — before any renaming happens, the script checks whether two different folders in the same parent directory would end up with the same proposed name. Collisions are flagged and both folders are skipped with a warning, preventing one from silently overwriting the other.

### Changed
- Track titles are now read alongside album tags in a single metadata pass, reducing the number of file reads.
- Conflict prompt rebuilt to show track titles per album group rather than just filenames.
- Report now includes a New Name column and a Files count column.
- Version bump to v2.0.

---

## [1.0] - 2026-03-14

### Added
- Initial release.
- Reads album tag from music files in each subfolder and renames the folder to match.
- Searches all folder depths recursively.
- **Conflict handling** — if files in a folder disagree on the album tag, prompts to choose between options, type a custom name, or skip.
- **Empty tag handling** — folders with no album tag are left unchanged with a warning.
- **`--pick` flag** — opens a native folder-picker dialog (tkinter). Allows selecting multiple folders by re-prompting after each selection.
- **`--path` flag** — override the default root folder path from the command line.
- **`--apply` flag** — dry run by default; `--apply` is required to rename for real.
- **Illegal character sanitisation** — characters forbidden in Windows folder names (`< > : " / \ | ? *`) are stripped from proposed names automatically.
- Same-parent collision check before renaming.
- Final y/n confirmation before any files are renamed.
