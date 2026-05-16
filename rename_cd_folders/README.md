# CD Folder Renamer

Finds folders named `CD #` (with a space) and renames them to `CD#` (no space).

**Examples:**
- `CD 1` → `CD1`
- `CD 2` → `CD2`
- `CD 10` → `CD10`

---

## Usage

```
python rename_cd_folders.py                      # dry run, opens folder picker
python rename_cd_folders.py --apply              # rename for real
python rename_cd_folders.py --path "C:\Music"    # specify folder
python rename_cd_folders.py --apply --path "C:\Music"
```

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
