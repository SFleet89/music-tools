# MusicBrainz Tagger Tools

A set of scripts for batch-tagging music folders using MusicBrainz data. Looks up releases by catalogue number, artist, or title, scores candidates using file metadata for confidence, then writes full tags and embeds cover art.

Nothing is changed until you run with `--apply`. Dry run by default.

---

## Scripts

| Script | Purpose |
|---|---|
| `anjuna_mb_lookup.py` | Anjuna-specific lookup — extracts ANJ*/ANJCD* catalogue numbers from folder names |
| `mb_lookup.py` | Generic lookup — works with any music collection |
| `anjuna_tagger.py` | Tags files using output from `anjuna_mb_lookup.py` |
| `mb_tagger.py` | Tags files using output from `mb_lookup.py` or any lookup CSV |
| `anjuna_lookup_viewer.html` | Interactive viewer for all lookup CSVs — review and select correct releases |

---

## Requirements

```
pip install mutagen
```

---

## Workflow

### Anjunabeats collection

```
# 1. Look up releases by ANJ catalogue number
python anjuna_mb_lookup.py

# 2. Open CSV in anjuna_lookup_viewer.html, review, export with selections

# 3. Dry run — preview tags and new folder names
python anjuna_tagger.py

# 4. Tag for real
python anjuna_tagger.py --apply
```

### Any other collection

```
# 1. Look up releases by catno / artist / title
python mb_lookup.py

# 2. Open CSV in anjuna_lookup_viewer.html, review, export with selections

# 3. Dry run
python mb_tagger.py

# 4. Tag for real
python mb_tagger.py --apply
```

---

## How mb_lookup.py finds releases

For each subfolder it tries these strategies in order, stopping as soon as results are found:

1. **Catalogue number** — extracted from `[brackets]` in the folder name (e.g. `[BH 118-5]`, `[Magik Muzik 801-1]`)
2. **Artist + Title** — parsed from `Artist - Title` structure in folder name
3. **Title only** — in case artist name doesn't match MB exactly
4. **Album tag from files** — reads the album tag from the music files themselves as a last resort

### Folder name formats supported

```
1999 - DJ Tiesto - Sparkles [BH 118-5] WEB
2001 - DJ Tiesto - Flight 643 [Magik Muzik 801-1] CD
Above & Beyond - Sun & Moon [ANJ196D] (2011)
Artist - Album Title (Year)
Artist - Album Title
```

---

## Scoring

Each candidate release is scored against your folder to rank results:

| Column | What it measures |
|---|---|
| `search_score` | How well the MB catalogue number / title matches your folder name |
| `meta_score` | How well the MB tracklist matches your local file tags |
| `combined_score` | Weighted average: search 60% + metadata 40% |
| `track_match_pct` | % of local track titles fuzzy-matched against MB tracklist |
| `count_match` | Whether local file count matches MB track count |

---

## Tags written

For every file in the folder:

- Title, Artist, Album Artist
- Track number (with total e.g. 3/12)
- Disc number (with total e.g. 1/2)
- Year / Date
- Label
- Catalogue number
- Cover art (from Cover Art Archive)

---

## Folder renaming

After tagging, each folder is renamed to:
```
Artist - Title (Year)
```

For example:
```
ANJ111 Signalrunners & Julie Thompson - These Shoulders
→ Signalrunners & Julie Thompson - These Shoulders (2008)

1999 - DJ Tiesto - Sparkles [BH 118-5] WEB
→ DJ Tiesto - Sparkles (1999)
```

---

## Flags

| Flag | Both taggers | Lookup scripts |
|---|---|---|
| `--apply` | Tag for real | — |
| `--skip-art` | Skip cover art | — |
| `--auto` | — | Auto-pick best match |
| `--review` | — | Flag all multi-results |

---

## After tagging

Run the tagged folders through Picard afterwards to confirm. Since the MBIDs are written into the file tags, Picard will recognise each release instantly rather than needing to search.

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Files

| File | Description |
|---|---|
| `anjuna_mb_lookup.py` | Anjuna-specific lookup |
| `anjuna_tagger.py` | Anjuna tagger |
| `mb_lookup.py` | Generic lookup |
| `mb_tagger.py` | Generic tagger |
| `anjuna_lookup_viewer.html` | Lookup viewer (works for all lookup CSVs) |
| `MB_Tagger_Run_Commands.txt` | Quick reference |
| `CHANGELOG.md` | Version history |
| `reports\` | Per-run CSV reports |
