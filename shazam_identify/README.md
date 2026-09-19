# Shazam Identify

Identifies audio files using the Shazam API and optionally writes the recognised
tags (Artist, Title, Album, Year) back to each file.

Useful for folders of untagged, mystery, or poorly-labelled audio files —
especially DJ edits, bootlegs, or files that AcoustID/MusicBrainz could not match.

## Requirements

```
pip install shazamio mutagen
```

`shazamio` uses the Shazam API unofficially. An internet connection is required.
FFmpeg must be installed and on your PATH (used internally by shazamio to fingerprint audio).

## Usage

| Launcher | What it does |
|---|---|
| Run - Shazam Identify (Dry Run).cmd | Pick a folder, identify files, show results — no tags written |
| Run - Shazam Identify (Apply).cmd | Pick a folder, identify files, write tags to matched files |
| Run - Shazam Identify (Skip Tagged, Dry Run).cmd | Dry run, skipping files that already have Artist + Title |

### Command-line flags

| Flag | Description |
|---|---|
| `--pick` | Open a folder picker dialog |
| `--path "C:\path"` | Specify folder directly |
| `--apply` | Write identified tags (default: dry run) |
| `--skip-tagged` | Skip files that already have Artist + Title tags |
| `--delay N` | Seconds between Shazam requests (default: 0.5) |

## Output

Each run saves a timestamped CSV report to `shazam_identify/reports/`:

| Column | Description |
|---|---|
| Filename | The audio file |
| Status | Identified / No match / Tagged / Error / Skipped (already tagged) |
| Shazam Artist | Artist returned by Shazam |
| Shazam Title | Track title returned by Shazam |
| Shazam Album | Album returned by Shazam |
| Shazam Year | Release year returned by Shazam |
| Original Artist | Tag value before any changes |
| Original Title | Tag value before any changes |

## Supported formats

MP3, FLAC, M4A, AAC, OGG

## Notes

- The script sends audio fingerprints to Shazam's servers. No audio data is stored.
- Rate limiting: a configurable delay (default 0.5s) is added between requests to
  avoid hitting Shazam's unofficial API limits.
- `shazamio` is an unofficial library — Shazam may change their API without notice.
