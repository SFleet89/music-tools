# Rename Undo

Reverses folder renames made by `rename_to_catno.py` using its CSV report as input.

Reads the report and, for each row with status `renamed`, moves the folder back to its original name. Does not touch any file tags.

---

## Usage

```
python rename_undo.py                            # opens file picker to select CSV
python rename_undo.py "C:\path\to\report.csv"
python rename_undo.py "C:\path\to\report.csv" --apply
```

---

## .cmd files

| File | What it does |
|---|---|
| `Run - Rename Undo (Dry Run).cmd` | Preview — shows what would be restored |
| `Run - Rename Undo (Apply).cmd` | Execute the undo |

---

## Notes

- Only rows with status `renamed` in the source CSV are processed.
- If the renamed folder no longer exists (already moved or deleted), the row is skipped with a warning.
- Reports saved to `rename_undo/reports/`.
