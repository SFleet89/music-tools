# AcousticID → MusicBrainz Tagger

Reads `ACOUSTID_ID` tags already written by `acoustid_fingerprint.py`, queries
MusicBrainz for full metadata (title, artist, album, date, label, catalogue
number, MB IDs), and writes the selected tags back to your audio files.

This is the built-in replacement for MusicBrainz Picard — no separate app needed.

---

## What it does

1. **Scans** a folder (recursively) for audio files that have an `ACOUSTID_ID` tag.
2. **Looks up** each AcoustID via the AcoustID API and fetches full metadata
   from MusicBrainz. Results are cached in `music_cache.db` — re-runs (and the
   apply pass after a dry run) make zero API calls.
3. **Classifies** each file into one of three states:
   - **Write all** — file has no existing tags; MB metadata written in full.
   - **Write IDs only** — existing tags match MB; only MB IDs are added.
   - **Flagged** — existing tags don't match MB; file is reported but not touched
     until reviewed in the GUI (or `--conflict mb_wins` is passed).
4. **Reports** every file to a timestamped CSV in `acoustid_mb_tagger/reports/`.

---

## Usage

```
Run - AcousticID MB Tagger (Dry Run).cmd    → preview what would be tagged
Run - AcousticID MB Tagger (Apply).cmd      → write tags (confirms before acting)
```

Or directly:

```
python acoustid_mb_tagger.py --pick
python acoustid_mb_tagger.py --pick --apply
python acoustid_mb_tagger.py --path "E:\Music\Artist\Album" --apply
python acoustid_mb_tagger.py --pick --conflict mb_wins --apply
```

### Flags

| Flag | Description |
|------|-------------|
| `--pick` | Open a folder picker dialog |
| `--path "C:\..."` | Specify folder directly |
| `--apply` | Write tags (dry run is default) |
| `--conflict flag` | Flag files where tags differ from MB (default) |
| `--conflict mb_wins` | MB metadata always overwrites existing tags |
| `--conflict keep_existing` | Never overwrite existing tags; write MB IDs only |

---

## Output (CSV columns)

| Column | Description |
|--------|-------------|
| `filepath` | Full path to the file |
| `filename` | Filename only |
| `acoustid_id` | AcoustID UUID read from the file tag |
| `status` | `would_tag` / `tagged` / `flagged` / `no_match` / `error` |
| `action` | `write_all` / `write_ids_only` / `flag` |
| `current_title/artist/album` | Tags currently in the file |
| `mb_title/artist/album/date` | Tags from MusicBrainz |
| `mb_recordingid` / `mb_albumid` | MusicBrainz IDs |
| `tags_written` | Comma-separated list of tags that were (or would be) written |
| `note` | Error or skip reason if any |

---

## Requirements

```
pip install requests mutagen musicbrainzngs
```

- `AcoustID API key` — set in `music_config.json` → `acoustid.api_key`
- Files must already have been processed by `acoustid_fingerprint.py`
  (i.e., they must have an `ACOUSTID_ID` tag)

---

## Supported formats

FLAC, MP3, M4A / AAC / ALAC, OGG Vorbis, Opus  
(WAV is attempted but has limited tag support)
