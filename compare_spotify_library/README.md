# compare_spotify_library

Compares a Spotify/Streamrip staging folder against your main music library.
Matches tracks by tags, compares quality (format + bitrate), and outputs a CSV
report so you can decide what to keep, upgrade, or skip.  **No files are moved
or deleted** — this script is report-only.

---

## What it does

1. Scans all audio files in your Spotify staging folder
2. Scans all audio files in your main library (`E:\Music`)
3. Reads tags from every file using mutagen
4. Matches Spotify tracks against library tracks using two strategies:
   - **Exact match**: AlbumArtist + Album + Title (all normalised)
   - **Loose match**: Artist + Title only (catches same song on a different album)
5. For each match, compares quality scores (format rank + bitrate)
6. Saves a CSV report — no files touched

---

## Quality scoring

| Format | Tier |
|--------|------|
| FLAC, ALAC, APE, WAV | Lossless (highest) |
| OGG, OPUS | High-quality lossy |
| M4A / AAC | Mid-quality lossy |
| MP3 | Standard lossy |
| WMA | Lower quality |

Within the same format tier, higher bitrate wins.

---

## CSV report columns

| Column | Description |
|--------|-------------|
| `match_type` | `exact`, `loose (title+artist, album differs)`, or `no match` |
| `recommendation` | `UPGRADE`, `SAME`, `SKIP`, or `NEW` |
| `spotify_file` | Full path of the Spotify file |
| `spotify_quality` | e.g. `FLAC (lossless)` or `MP3 320kbps` |
| `library_file` | Full path of the matched library file (blank if no match) |
| `library_quality` | Quality of the library copy |
| `albumartist` | From Spotify file tags |
| `album` | From Spotify file tags |
| `title` | From Spotify file tags |
| `note` | Tag read errors, if any |

### Recommendation values
- **UPGRADE** — Spotify copy is higher quality; consider replacing the library copy
- **SAME** — equal quality; keep the library copy
- **SKIP** — library copy is better; Spotify copy not needed
- **NEW** — track not found in library at all; candidate for adding

---

## Usage

```
python compare_spotify_library.py --pick-spotify --pick-library
python compare_spotify_library.py --path-spotify "C:\...\Organized" --path-library "E:\Music"
```

Or double-click the `.cmd` launcher.

---

## Flags

| Flag | Description |
|------|-------------|
| `--pick-spotify` | Folder dialog for the Spotify staging folder |
| `--path-spotify "C:\..."` | Supply Spotify path directly |
| `--pick-library` | Folder dialog for the main music library |
| `--path-library "E:\..."` | Supply library path directly |

---

## Requirements

```
pip install mutagen
```

Scanning a large library (tens of thousands of tracks) can take a few minutes.
