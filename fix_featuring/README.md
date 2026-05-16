# Fix Featuring Tags

Moves featuring credits from the Artist tag to the Title tag across all audio files in a folder.

**Before:**
- Artist: `Above & Beyond feat. Zoë Johnston`
- Title: `Sun & Moon`

**After:**
- Artist: `Above & Beyond`
- Title: `Sun & Moon (feat. Zoë Johnston)`

If the title already contains a featuring credit, only the Artist tag is cleaned — the credit is not added twice. Only the Artist tag is modified; Album Artist is left untouched.

---

## Requirements

```
pip install mutagen
```

---

## Usage

```
python fix_featuring.py                       # dry run, opens folder picker
python fix_featuring.py --apply               # scan and apply, opens folder picker
python fix_featuring.py --from-csv            # apply from a previous dry-run CSV
```

Run without `--apply` first to preview all changes in the CSV report before committing.

---

## .cmd files

| File | What it does |
|---|---|
| `Run - Fix Featuring (Dry Run).cmd` | Preview changes — nothing is written |
| `Run - Fix Featuring (Apply).cmd` | Apply changes to tags |
| `fix_featuring_apply_from_csv.cmd` | Apply from a previously saved dry-run CSV |

---

## Featuring formats handled

`feat.`, `ft.`, `featuring` — with or without surrounding brackets.

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Reports

Saved to `fix_featuring/reports/fix_featuring_YYYYMMDD_HHMMSS_dry.csv` or `_applied.csv`.

Columns: `file_path`, `original_artist`, `new_artist`, `original_title`, `new_title`, `status`, `notes`

Status values: `pending`, `modified`, `no_featuring`, `skipped`, `error`
