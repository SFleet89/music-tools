# mbz2cue

Extracts a tracklist from a MusicBrainz release page and generates a `.cue` sheet file.

Handles multi-disc releases — generates a separate `.cue` file per disc (e.g. `album_disc1.cue`, `album_disc2.cue`).

---

## Requirements

```
pip install requests beautifulsoup4
```

---

## Usage

```
python mbz2cue.py --url "https://musicbrainz.org/release/..." --wav_filename "album.wav"
python mbz2cue.py --url "..." --wav_filename "album.wav" --output_file "album.cue"
python mbz2cue.py --url "..." --wav_filename "album.wav" --debug_level 2
```

---

## Flags

| Flag | Description |
|---|---|
| `--url` | MusicBrainz release URL (required) |
| `--wav_filename` | WAV file name to reference in the CUE (required) |
| `--output_file` | Output CUE filename (default: album title) |
| `--debug_level` | 0 = silent, 1 = errors, 2 = info, 3 = debug |

---

## Notes

- This tool uses HTML scraping (not the MusicBrainz API). If MusicBrainz changes their page layout, it may break.
- For tagged FLAC files, `flac_to_cue.py` is the preferred tool — it reads the `MUSICBRAINZ_ALBUMID` tag directly and uses the proper JSON API.
- `mbz2cue.py` is useful when you have an untagged WAV file and a MusicBrainz URL.
- No dry-run mode — the script writes the CUE file immediately on run.
