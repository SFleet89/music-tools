# Rename to CATNO

Renames album folders to `CATNO - Album Name` format.

**Example:** `Above & Beyond - We Are All We Need (2015)` → `ANJCD043 - We Are All We Need`

Reads the catalogue number and album name from the embedded tags of the first audio file found in each folder. If no `CATALOGNUMBER` tag is present (or the tag contains a placeholder like `none`), falls back to parsing the catno directly from the folder name using ANJ/ANJCD/ANJDEEP pattern matching.

Scans recursively — any folder that directly contains audio files is treated as an album folder.

---

## Requirements

```
pip install mutagen
```

---

## Usage

```
python rename_to_catno.py                        # dry run, opens folder picker
python rename_to_catno.py --apply                # rename for real, opens folder picker
python rename_to_catno.py "C:\path\to\Music"     # specify folder
python rename_to_catno.py "C:\path\to\Music" --apply
```

---

## .cmd files

| File | What it does |
|---|---|
| `Run - Rename to CatNo (Dry Run).cmd` | Preview renames — nothing is moved |
| `Run - Rename to CatNo (Apply).cmd` | Execute renames |

---

## Name formatting rules

- Catno normalised to no-hyphen format: `ANJ-001` → `ANJ001`
- Album ` / ` separators replaced with ` & ` (double A-side releases)
- Double spaces collapsed after sanitising
- Windows-illegal characters stripped

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Reports

Saved to `rename_to_catno/reports/rename_to_catno_YYYYMMDD_HHMMSS.csv`.

To undo renames, use `rename_undo.py` with the report CSV.
