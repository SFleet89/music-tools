"""
Anjuna MusicBrainz Tagger  v1.1
================================
Reads an exported anjuna_lookup CSV (from anjuna_lookup_viewer.html),
fetches full release data from MusicBrainz for each matched folder,
writes tags to all music files, embeds cover art, and renames the folder
to: Artist - Title (Year)

Requirements:
    pip install mutagen

Usage:
    python anjuna_tagger.py                              # opens file picker, dry run
    python anjuna_tagger.py --apply                      # opens file picker, tag for real
    python anjuna_tagger.py "path\\to\\lookup.csv"       # dry run with specific CSV
    python anjuna_tagger.py "path\\to\\lookup.csv" --apply   # tag for real
    python anjuna_tagger.py "path\\to\\lookup.csv" --skip-art # skip cover art

Output:
    Reports saved to: <script folder>\\reports\\anjuna_tagger_YYYYMMDD_HHMMSS.csv
"""

import sys
import os
import re
import csv
import json
import time
import shutil
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    from mutagen.flac import FLAC, Picture
    from mutagen.mp3 import MP3
    from mutagen.id3 import (
        ID3, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, TPUB, TXXX,
        APIC, error as ID3Error
    )
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("ERROR: mutagen is not installed.")
    print("       Run: pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
MB_API_BASE          = "https://musicbrainz.org/ws/2"
MB_COVER_API         = "https://coverartarchive.org/release"
USER_AGENT           = "AnjunaTagger/1.1 ( music-tools )"
REQUEST_DELAY        = 1.1
SCRIPT_DIR           = Path(__file__).parent

# ── Flags ──────────────────────────────────────────────────────────────────────
APPLY    = "--apply"    in sys.argv
SKIP_ART = "--skip-art" in sys.argv
DRY_RUN  = not APPLY

# ── Rate limiting ──────────────────────────────────────────────────────────────
_last_request = 0

def mb_get(url):
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _last_request = time.time()
    return data


def mb_fetch_release(mbid):
    params = urllib.parse.urlencode({
        "inc": "recordings artist-credits labels release-groups",
        "fmt": "json",
    })
    return mb_get("%s/release/%s?%s" % (MB_API_BASE, mbid, params))


def fetch_cover_art(mbid):
    try:
        url = "%s/%s/front" % (MB_COVER_API, mbid)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception:
        return None


# ── Release data extraction ────────────────────────────────────────────────────

def get_release_year(release):
    date = release.get("date", "") or ""
    if date:
        return date[:4]
    rg   = release.get("release-group", {})
    date = rg.get("first-release-date", "") or ""
    return date[:4] if date else ""


def get_label(release):
    for li in release.get("label-info", []):
        label = (li.get("label") or {}).get("name", "")
        if label:
            return label
    return ""


def get_catno(release):
    for li in release.get("label-info", []):
        catno = li.get("catalog-number", "")
        if catno:
            return catno
    return ""


def get_album_artist(release):
    credits = release.get("artist-credit", [])
    parts   = []
    for c in credits:
        if isinstance(c, dict):
            name = c.get("name") or (c.get("artist") or {}).get("name", "")
            join = c.get("joinphrase", "")
            if name:
                parts.append(name + join)
    return "".join(parts).strip() or "Various Artists"


def get_tracks(release):
    tracks    = []
    media     = release.get("media", [])
    disc_count = len(media)
    for disc_idx, medium in enumerate(media, 1):
        medium_tracks = medium.get("tracks", [])
        total         = len(medium_tracks)
        for t in medium_tracks:
            rec      = t.get("recording") or {}
            t_credits = (t.get("artist-credit") or
                         rec.get("artist-credit") or
                         release.get("artist-credit", []))
            t_parts  = []
            for c in t_credits:
                if isinstance(c, dict):
                    name = c.get("name") or (c.get("artist") or {}).get("name", "")
                    join = c.get("joinphrase", "")
                    if name:
                        t_parts.append(name + join)
            tracks.append({
                "title":          t.get("title") or rec.get("title", ""),
                "position":       t.get("number") or str(t.get("position", "")),
                "track_number":   t.get("position", 0),
                "disc_number":    disc_idx,
                "disc_count":     disc_count,
                "total_tracks":   total,
                "artist":         "".join(t_parts).strip(),
                "recording_mbid": rec.get("id", ""),
            })
    return tracks


def sanitise_folder_name(name):
    for ch in r'<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip(". ")


def build_folder_name(release, album_artist, year):
    title  = sanitise_folder_name(release.get("title", "Unknown"))
    artist = sanitise_folder_name(album_artist or "Unknown Artist")
    if year:
        return "%s - %s (%s)" % (artist, title, year)
    return "%s - %s" % (artist, title)


# ── File matching ──────────────────────────────────────────────────────────────

def get_music_files(folder):
    folder  = Path(folder)
    _CD_RE  = re.compile(r'^(cd|disc|disk)\s*\d+$', re.IGNORECASE)
    subdirs = [d for d in folder.iterdir() if d.is_dir()]
    cd_dirs = [d for d in subdirs if _CD_RE.match(d.name)]

    if cd_dirs and len(cd_dirs) == len(subdirs):
        files = []
        for cd in sorted(cd_dirs):
            files.extend(sorted(
                f for f in cd.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            ))
        return files

    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def match_files_to_tracks(files, tracks):
    sorted_tracks = sorted(tracks, key=lambda t: (t["disc_number"], t["track_number"]))
    count = min(len(files), len(sorted_tracks))
    return list(zip(files[:count], sorted_tracks[:count]))


# ── Tag writing ────────────────────────────────────────────────────────────────

def write_tags_flac(path, track, release, album_artist, year, label, catno, art_bytes):
    audio = FLAC(path)
    audio["title"]         = [track["title"]]
    audio["artist"]        = [track["artist"] or album_artist]
    audio["albumartist"]   = [album_artist]
    audio["album"]         = [release.get("title", "")]
    audio["tracknumber"]   = ["%d/%d" % (track["track_number"], track["total_tracks"])]
    audio["discnumber"]    = ["%d/%d" % (track["disc_number"], track["disc_count"])]
    audio["date"]          = [year]
    audio["year"]          = [year]
    if label:  audio["organization"]  = [label]
    if catno:  audio["catalognumber"] = [catno]
    if art_bytes:
        pic      = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.desc = "Cover"
        pic.data = art_bytes
        audio.clear_pictures()
        audio.add_picture(pic)
    audio.save()


def write_tags_mp3(path, track, release, album_artist, year, label, catno, art_bytes):
    try:
        audio = ID3(path)
    except ID3Error:
        audio = ID3()
    for tag in ["TIT2","TPE1","TPE2","TALB","TRCK","TPOS","TDRC","TPUB","APIC","TXXX:CATALOGNUMBER"]:
        audio.delall(tag)
    audio["TIT2"] = TIT2(encoding=3, text=track["title"])
    audio["TPE1"] = TPE1(encoding=3, text=track["artist"] or album_artist)
    audio["TPE2"] = TPE2(encoding=3, text=album_artist)
    audio["TALB"] = TALB(encoding=3, text=release.get("title", ""))
    audio["TRCK"] = TRCK(encoding=3, text="%d/%d" % (track["track_number"], track["total_tracks"]))
    audio["TPOS"] = TPOS(encoding=3, text="%d/%d" % (track["disc_number"], track["disc_count"]))
    audio["TDRC"] = TDRC(encoding=3, text=year)
    if label: audio["TPUB"] = TPUB(encoding=3, text=label)
    if catno: audio["TXXX:CATALOGNUMBER"] = TXXX(encoding=3, desc="CATALOGNUMBER", text=catno)
    if art_bytes:
        audio["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=art_bytes)
    audio.save(path, v2_version=3)


def write_tags_m4a(path, track, release, album_artist, year, label, catno, art_bytes):
    audio = MP4(path)
    audio["\xa9nam"] = [track["title"]]
    audio["\xa9ART"] = [track["artist"] or album_artist]
    audio["aART"]    = [album_artist]
    audio["\xa9alb"] = [release.get("title", "")]
    audio["trkn"]    = [(track["track_number"], track["total_tracks"])]
    audio["disk"]    = [(track["disc_number"], track["disc_count"])]
    audio["\xa9day"] = [year]
    if label: audio["----:com.apple.iTunes:LABEL"]         = [label.encode("utf-8")]
    if catno: audio["----:com.apple.iTunes:CATALOGNUMBER"] = [catno.encode("utf-8")]
    if art_bytes:
        audio["covr"] = [MP4Cover(art_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def write_tags(path, track, release, album_artist, year, label, catno, art_bytes):
    ext = Path(path).suffix.lower()
    if ext == ".flac":
        write_tags_flac(path, track, release, album_artist, year, label, catno, art_bytes)
    elif ext == ".mp3":
        write_tags_mp3(path, track, release, album_artist, year, label, catno, art_bytes)
    elif ext in (".m4a", ".aac"):
        write_tags_m4a(path, track, release, album_artist, year, label, catno, art_bytes)
    else:
        audio = MutagenFile(path, easy=True)
        if audio:
            audio["title"]       = [track["title"]]
            audio["artist"]      = [track["artist"] or album_artist]
            audio["albumartist"] = [album_artist]
            audio["album"]       = [release.get("title", "")]
            audio["tracknumber"] = ["%d/%d" % (track["track_number"], track["total_tracks"])]
            audio["discnumber"]  = ["%d/%d" % (track["disc_number"], track["disc_count"])]
            audio["date"]        = [year]
            audio.save()


# ── CSV loading ────────────────────────────────────────────────────────────────

def load_csv(csv_path):
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def filter_actionable(rows):
    return [
        r for r in rows
        if r.get("mbid", "").strip() and r.get("folder_path", "").strip()
    ]


# ── Main processing ────────────────────────────────────────────────────────────

def process_folder(row, dry_run, skip_art):
    folder_path = Path(row["folder_path"].strip())
    mbid        = row["mbid"].strip()
    folder_name = row.get("folder", folder_path.name)

    result = {
        "folder":       folder_name,
        "folder_path":  str(folder_path),
        "mbid":         mbid,
        "status":       "",
        "new_folder":   "",
        "files_tagged": 0,
        "notes":        "",
    }

    if not folder_path.exists():
        result["status"] = "error"
        result["notes"]  = "Folder not found: %s" % folder_path
        return result

    files = get_music_files(folder_path)
    if not files:
        result["status"] = "skipped"
        result["notes"]  = "No music files found"
        return result

    try:
        release = mb_fetch_release(mbid)
    except Exception as e:
        result["status"] = "error"
        result["notes"]  = "MB fetch failed: %s" % e
        return result

    album_artist     = get_album_artist(release)
    year             = get_release_year(release)
    label            = get_label(release)
    catno            = get_catno(release)
    tracks           = get_tracks(release)
    pairs            = match_files_to_tracks(files, tracks)
    new_folder_name  = build_folder_name(release, album_artist, year)
    new_folder_path  = folder_path.parent / new_folder_name
    result["new_folder"] = new_folder_name

    count_note = ""
    if len(files) != len(tracks):
        count_note = "file count mismatch (local=%d MB=%d) — tagged %d" % (
            len(files), len(tracks), len(pairs))

    if dry_run:
        result["status"]       = "would_tag"
        result["files_tagged"] = len(pairs)
        result["notes"]        = count_note or ("would tag %d file(s), rename folder" % len(pairs))
        return result

    # Fetch cover art
    art_bytes = None
    if not skip_art:
        art_bytes = fetch_cover_art(mbid)

    # Write tags
    tagged = 0
    errors = []
    for f, track in pairs:
        try:
            write_tags(str(f), track, release, album_artist, year, label, catno, art_bytes)
            tagged += 1
        except Exception as e:
            errors.append("%s: %s" % (f.name, e))

    result["files_tagged"] = tagged

    # Rename folder
    if folder_path != new_folder_path:
        try:
            if new_folder_path.exists():
                counter = 1
                base = new_folder_name
                while new_folder_path.exists():
                    new_folder_name = "%s (%d)" % (base, counter)
                    new_folder_path = folder_path.parent / new_folder_name
                    counter += 1
                result["new_folder"] = new_folder_name
            shutil.move(str(folder_path), str(new_folder_path))
        except Exception as e:
            errors.append("Rename failed: %s" % e)

    if errors:
        result["status"] = "partial"
        result["notes"]  = (count_note + " | " if count_note else "") + "; ".join(errors)
    else:
        result["status"] = "tagged"
        result["notes"]  = count_note or ""

    return result


# ── Report ─────────────────────────────────────────────────────────────────────

FIELDNAMES = ["folder", "folder_path", "mbid", "status", "new_folder", "files_tagged", "notes"]

def write_report(results, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results, dry_run, output_path):
    from collections import Counter
    counts = Counter(r["status"] for r in results)
    print()
    print("=" * 60)
    print("  SUMMARY%s" % (" [DRY RUN]" if dry_run else ""))
    print("=" * 60)
    if dry_run:
        print("  Would tag      : %d" % counts.get("would_tag", 0))
    else:
        print("  Tagged         : %d" % counts.get("tagged", 0))
        print("  Partial        : %d" % counts.get("partial", 0))
    print("  Skipped        : %d" % counts.get("skipped", 0))
    print("  Errors         : %d" % counts.get("error", 0))
    print()
    print("  Report saved to:")
    print("  %s" % output_path)
    print("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askopenfilename(
                title="Select lookup CSV to tag from",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialdir=str(SCRIPT_DIR / "reports"),
            )
            root.destroy()
            if not chosen:
                print("No file selected. Exiting.")
                sys.exit(0)
            csv_path = Path(chosen)
        except Exception as e:
            print("ERROR: Could not open file picker: %s" % e)
            print("Usage: python anjuna_tagger.py [path_to_csv] [--apply] [--skip-art]")
            sys.exit(1)
    else:
        csv_path = Path(args[0].strip('"'))

    if not csv_path.exists():
        print("ERROR: CSV not found: %s" % csv_path)
        sys.exit(1)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    suffix      = "_dry" if DRY_RUN else "_applied"
    output_path = reports_dir / ("anjuna_tagger%s_%s.csv" % (suffix, timestamp))

    print()
    print("=" * 60)
    print("  Anjuna MusicBrainz Tagger  v1.1")
    print("=" * 60)
    print("  CSV       : %s" % csv_path)
    print("  Mode      : %s" % ("DRY RUN — nothing will be changed" if DRY_RUN else "LIVE — files will be tagged"))
    print("  Cover art : %s" % ("disabled" if SKIP_ART else "enabled"))
    print("  Output    : %s" % output_path)
    print("=" * 60)

    all_rows   = load_csv(str(csv_path))
    actionable = filter_actionable(all_rows)
    skipped    = len(all_rows) - len(actionable)

    print()
    print("  Total rows in CSV   : %d" % len(all_rows))
    print("  Rows with MBID      : %d" % len(actionable))
    print("  Rows without MBID   : %d (skipped)" % skipped)
    print()

    if not DRY_RUN:
        confirm = input("  Tag %d folder(s)? (y/n): " % len(actionable)).strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            return
        print()

    results = []
    for idx, row in enumerate(actionable, 1):
        folder_name = row.get("folder", "")
        print("  [%d/%d]  %s" % (idx, len(actionable), folder_name))
        result = process_folder(row, DRY_RUN, SKIP_ART)
        symbol = {"tagged":"✓","would_tag":"~","partial":"!","skipped":"-","error":"✗"}.get(result["status"],"?")
        if result["status"] in ("tagged", "would_tag"):
            print("          %s %d file(s) → %s" % (symbol, result["files_tagged"], result["new_folder"]))
        else:
            print("          %s %s" % (symbol, result["notes"]))
        results.append(result)

    write_report(results, str(output_path))
    print_summary(results, DRY_RUN, str(output_path))


if __name__ == "__main__":
    main()
