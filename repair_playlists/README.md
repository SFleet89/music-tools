# Playlist Repair Tool

Scans `.m3u` playlist files and repairs broken paths by searching your music library for each track.

Each track entry is placed into one of three buckets:

| Category | Description |
|---|---|
| **Resolved** | Single confident match found — path updated automatically |
| **Ambiguous** | Multiple possible matches — you choose via HTML selector |
| **Missing** | No match found — entry kept in playlist with a `# REPAIR_MISSING` comment |

Unresolved and missing entries are preserved in the repaired playlist with comments so no information is lost.

---

## Requirements

```
pip install rapidfuzz
```

(`difflib` used as fallback if `rapidfuzz` is not installed)

---

## Usage

```
python repair_playlists.py                      # dry run, opens folder pickers
python repair_playlists.py --apply              # repair and write playlists
python repair_playlists.py --playlists "C:\Playlists" --music "E:\Music"
python repair_playlists.py --selections picks.json --apply
```

---

## .cmd files

| File | What it does |
|---|---|
| `Run - Repair Playlists (Dry Run).cmd` | Scan and preview — nothing is written |
| `Run - Repair Playlists (Apply).cmd` | Write repaired playlists |

After each dry run, the script also generates updated `.cmd` files with the selected paths saved in for quick re-running.

---

## Ambiguous matches

When multiple library files could match a playlist entry, an HTML selector is generated. Open it in a browser, pick the correct file for each ambiguous entry, download the `selections.json`, then re-run with `--selections selections.json --apply`.

---

## Reports

Saved to `repair_playlists/reports/`:
- CSV — all entries with status and matched paths
- `.txt` — missing tracks only
- HTML selector — ambiguous matches for manual review
