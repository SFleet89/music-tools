# CD Folder Renamer

Finds folders named `CD #` (with a space) and renames them to `CD#` (no space).

**Examples:**
- `CD 1` → `CD1`
- `CD 2` → `CD2`
- `CD 10` → `CD10`

---

## Usage

```
python rename_cd_folders.py                         # dry run, opens folder picker
python rename_cd_folders.py --apply                 # rename for real
python rename_cd_folders.py --path "C:\Music"       # specify folder
python rename_cd_folders.py --apply --path "C:\Music"
python rename_cd_folders.py --depth 2               # only scan folders exactly 2 levels below root
python rename_cd_folders.py --apply --depth 2       # rename at exactly 2 levels below root
```

### `--depth N`

Limits the scan to folders that are **exactly N levels** below the root.

| Command | Folders checked |
|---|---|
| *(no --depth)* | Every subfolder at any depth |
| `--depth 1` | `root/FolderName` only |
| `--depth 2` | `root/Parent/FolderName` only |
| `--depth 3` | `root/A/B/FolderName` only |

This is useful when your library is structured consistently — for example, if all CD subfolders live two levels down (`Artist / Album / CD 1`), `--depth 3` will skip anything at other levels and run faster.

---

## .cmd files

| File | What it does |
|---|---|
| `Run - Rename CD Folders (Dry Run).cmd` | Preview — nothing is renamed |
| `Run - Rename CD Folders (Apply).cmd` | Execute renames |

---

## Notes

- Skips if the destination name already exists.
- Reports saved to `rename_cd_folders/reports/`.
