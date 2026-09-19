# Move For Review

Reads an `acoustid_fingerprint` CSV report and moves album folders that contain
unidentified or mismatched tracks into a review folder for manual inspection.

## What it does

After running `acoustid_fingerprint --apply`, you get a CSV where each row has a
`status` of either `identified` or `no_match`. This script:

1. Reads that CSV and collects all `no_match` filenames, plus any filenames that
   appear in the hardcoded `BAD_FINGERPRINT_FILES` list (tracks that AcoustID
   fingerprinted to the wrong song).
2. Scans the **source** folder to find where each flagged file lives.
3. Moves the entire **album folder** (artist/album/) — not just the individual
   track — to the **destination** review folder, preserving the relative path
   (`artist/album/` structure is kept intact).

This way, unrecognised albums land in a tidy review folder where you can manually
check, re-tag, or delete them without cluttering the main library.

## Undo

Every apply run saves a `move_for_review_applied_*.csv` to the `reports/` folder.
Running with `--undo --csv <that_csv>` (dry run) or `--undo --csv <that_csv> --apply`
will restore all moved albums back to their original locations.

## Usage

Double-click a launcher:

| File | What it does |
|------|-------------|
| `Run - Move For Review (Dry Run).cmd` | Preview which albums would be moved — no changes made |
| `Run - Move For Review (Apply).cmd` | Move the albums |
| `Run - Move For Review Undo (Dry Run).cmd` | Preview restoring moved albums |
| `Run - Move For Review Undo (Apply).cmd` | Restore moved albums to original locations |

Each launcher opens file/folder pickers — no paths to type.

Or run from the command line:

```
python move_for_review.py --csv <acoustid_csv> --source <organized> --dest <review_folder>
python move_for_review.py --csv <acoustid_csv> --source <organized> --dest <review_folder> --apply
python move_for_review.py --undo --csv <move_for_review_applied_csv>
python move_for_review.py --undo --csv <move_for_review_applied_csv> --apply
```

## Flags

| Flag | Description |
|------|-------------|
| `--csv` | Path to the acoustid CSV (or move_for_review_applied CSV for undo) |
| `--source` | Source folder to scan for flagged files |
| `--dest` | Destination folder for albums needing review |
| `--apply` | Execute the moves (default is dry run) |
| `--undo` | Restore mode — reads a move_for_review_applied CSV and moves albums back |

## Reports

Every run (dry and apply) saves a timestamped CSV to `reports/`:

| Column | Description |
|--------|-------------|
| `item` | Relative path of the album folder (`Artist/Album`) |
| `status` | `would_move` / `moved` / `would_restore` / `restored` / `error` |
| `source` | Full path of the source location |
| `dest` | Full path of the destination location |
| `error` | Error message if the move failed |

## Notes

- The `BAD_FINGERPRINT_FILES` list near the top of the script contains filenames
  known to fingerprint to the wrong song. Edit this list as you discover more.
- Moves use `shutil.move`, so cross-drive moves (C: → E:) work correctly.
- No Python packages required beyond the standard library.
