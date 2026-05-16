# CD Folder Renamer

Finds folders named `CD #` (with a space) and renames them to `CD#` (no space).

**Examples:**
- `CD 1` → `CD1`
- `CD 2` → `CD2`
- `CD 10` → `CD10`

---

## Usage

```
python rename_cd_folders.py                          # dry run, opens folder picker
python rename_cd_folders.py --apply                  # rename for real
python rename_cd_folders.py --path "C:\Music"        # specify folder
python rename_cd_folders.py --apply --path "C:\Music"
python rename_cd_folders.py --depth 2                # only scan folders exactly 2 levels deep
python rename_cd_folders.py --depth 2 --apply        # scan at depth 2 and rename
```

### Flags

| Flag | Description |
|---|---|
| `--pick` | Open a folder-picker dialog to choose the root folder |
| `--path "C:\..."` | Specify the root folder directly |
| `--apply` | Actually perform renames (default is dry run — nothing is changed) |
| `--depth N` | Only scan folders that are exactly N levels below the root. Omit to scan all depths. |

#### What `--depth` means

Depth is counted from the root folder you select. For example, given:

```
E:\Music\
    Artist A\
        Album 1\
            CD 1\        ← depth 3
        CD 2\            ← depth 2
    CD 3\                ← depth 1
```

- `--depth 1` would only consider `CD 3`
- `--depth 2` would only consider `CD 2`
- `--depth 3` would only consider `CD 1`
- No `--depth` flag scans all of them

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
