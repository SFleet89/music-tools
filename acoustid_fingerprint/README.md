# AcousticID Fingerprint

Generates Chromaprint audio fingerprints for every audio file in a folder,
optionally looks up each fingerprint against the AcousticID API to retrieve
MusicBrainz recording IDs, and optionally writes the results as tags directly
into the audio files.

Fingerprints are stored in `music_cache.db` (fp_cache table) for use by the
duplicate finder. Tag-writing requires `--apply`.

## Usage

Run via the GUI (AcousticID Fingerprint panel) or from the command line:

```
python acoustid_fingerprint.py --pick                        # dry run — no tags written
python acoustid_fingerprint.py --pick --apply                # fingerprint + lookup + write tags
python acoustid_fingerprint.py --path "C:\path\to\folder"   # non-interactive
python acoustid_fingerprint.py --pick --no-lookup            # fingerprint only, skip API
python acoustid_fingerprint.py --pick --include-cached       # re-process all files
python acoustid_fingerprint.py --pick --min-confidence 0.90  # stricter confidence threshold
```

## Launchers

| File | What it does |
|------|-------------|
| `Run - AcousticID Fingerprint (Fingerprint + Lookup).cmd` | Dry run — shows what would be tagged |
| `Run - AcousticID Fingerprint (Write Tags).cmd` | Apply — fingerprint, look up, and write tags |
| `Run - AcousticID Fingerprint (Fingerprint Only).cmd` | Fingerprint only, no API call |

## Flags

| Flag                     | Description                                                 |
|--------------------------|-------------------------------------------------------------|
| `--pick`                 | Open a folder dialog to select the folder                   |
| `--path "..."`           | Supply the folder path directly                             |
| `--apply`                | Write tags to files (default: dry run, no files modified)   |
| `--min-confidence 0.80`  | Minimum AcousticID score to write tags (default 0.80)       |
| `--no-lookup`            | Skip AcousticID API — fingerprint and cache only            |
| `--include-cached`       | Re-fingerprint files already in the cache                   |

## Tags written (apply mode)

| Format        | Tags written                                                      |
|---------------|-------------------------------------------------------------------|
| FLAC          | `MUSICBRAINZ_TRACKID`, `ACOUSTID_ID`, `ACOUSTID_FINGERPRINT`      |
| MP3           | `TXXX:MusicBrainz Recording Id`, `TXXX:AcoustID Id`, `TXXX:AcoustID Fingerprint` |
| M4A/AAC/ALAC  | `----:com.apple.iTunes:MusicBrainz Recording Id` etc.             |
| OGG / Opus    | Same Vorbis comment fields as FLAC                                |

Files below `--min-confidence` are not tagged and appear as `low_conf` in the report.

## Configuration

Set the following in `music_config.json` → `acoustid`:

- `fpcalc_path` — full path to fpcalc.exe (already set)
- `api_key` — your AcousticID client API key (free at https://acoustid.org/login)

## Output

- **fp_cache table** in `music_cache.db` — fingerprint + duration per file
- **CSV report** in `reports/` — filename, status, duration, AcousticID score,
  AcousticID ID, MusicBrainz recording ID, matched title and artist, tagged status.
  Report filename: `acoustid_fingerprint_dry_<timestamp>.csv` or `_applied_<timestamp>.csv`

## Requirements

```
pip install requests mutagen
```

fpcalc.exe must be present (path set in music_config.json).
