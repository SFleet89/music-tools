# Changelog — rename_album_folders.py

All notable changes to the Album Folder Renamer are documented here.

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
