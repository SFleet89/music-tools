"""
move_for_review.py — v1.3
Reads an acoustid_fingerprint CSV report and moves the album folders
containing no_match files and bad-fingerprint files to a review folder.

Moves the album folder (artist/album/) not just the individual file,
preserving the relative path structure under the source folder.

Usage — move (dry run):
  python move_for_review.py --csv <acoustid_csv> --source <organized> --dest <review_folder>

Usage — move (apply):
  python move_for_review.py --csv <acoustid_csv> --source <organized> --dest <review_folder> --apply

Usage — undo a previous apply (dry run):
  python move_for_review.py --undo --csv <move_for_review_applied_csv>

Usage — undo (apply):
  python move_for_review.py --undo --csv <move_for_review_applied_csv> --apply
"""

import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime

# ── Flags ────────────────────────────────────────────────────────────────────

DRY_RUN   = "--apply" not in sys.argv
UNDO_MODE = "--undo"  in sys.argv

def _flag(name):
    return next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == name and i + 1 < len(sys.argv)),
        None,
    )

CSV_PATH   = _flag("--csv")
SOURCE_DIR = _flag("--source")
DEST_DIR   = _flag("--dest")

# ── Bad-fingerprint files (wrong song matched by AcousticID) ─────────────────
# Files where AcoustID returned a high-confidence match but identified the
# wrong song. Add filenames here as you discover them; their album folder
# will be moved to the review destination on the next --apply run.
BAD_FINGERPRINT_FILES = {
    # ── Pre-existing (from earlier runs) ────────────────────────────────────
    "06. OneRepublic - I Lived.flac",
    "03. OneRepublic - Secrets.flac",
    "03. Jackson 5 - I Want You Back.flac",
    "01. Shaboozey - A Bar Song (Tipsy).flac",
    "04. Justin Timberlake - My Love.flac",
    # ── Added 2026-06-18 (acoustid_fingerprint_applied_20260618_204854) ─────
    "06. 3 Doors Down - Here Without You (Album Version).flac",
    "01. Sukhwinder Singh - Chaiyya Chaiyya.flac",
    '01. Alicia Keys - Lifeline (From the Original Motion Picture "The Color Purple").flac',
    "06. Alicia Keys - If I Ain't Got You.flac",
    "01. Allen Watts - ShellShock.flac",
    "01. Angelina Jordan - Bohemian Rhapsody.flac",
    "01. Anyma - Eternity.flac",
    "01. Benson Boone - Beautiful Things.flac",
    "13. blink-182 - I Miss You.flac",
    "10. Boards of Canada - Roygbiv.flac",
    "12. Busta Rhymes and Mariah Carey featuring The Flipmode Squad - I Know What You Want.flac",
    "01. Chris Cornell - Nearly Forgot My Broken Heart.flac",
    "02. Crazy Frog - Axel F.flac",
    "06. Daft Punk - Fresh.flac",
    "02. Dillon Francis - Get Low.flac",
    "11. Disturbed - Sacrifice.flac",
    "11. Disturbed - The Sound of Silence.flac",
    "01. Dominik Hauser - Stargate Atlantis - Main Title (Joel Goldsmith).flac",
    "12. Don Omar - Danza Kuduro.flac",
    "04. Five For Fighting - Chances.flac",
    "04. Five For Fighting - 100 Years (Album Version).flac",
    "01. Fleurie, Legends of Runeterra - Breathe (Legends of Runeterra Version).flac",
    "03. G-Eazy - Me, Myself & I.flac",
    "03. Gotye - Somebody That I Used To Know.flac",
    "08. Halo - Greatest Journey.flac",
    "08. Halo - The Gun Pointed At the Head of the Universe.flac",
    "10. Halo - Under Cover of Night.flac",
    "14. Halo - Covenant Dance.flac",
    "20. Halo - Perchance to Dream.flac",
    "01. Halo - Halo Theme Mjolnir Mix.flac",
    "04. Isao Tomita - Suite Bergamasque Clair de Lune, No. 3.flac",
    "05. Jay Z - Empire State Of Mind.flac",
    "02. Jay Z - Run This Town (Album Version (Edited)).flac",
    "16. Jay Z - Numb  Encore (Live At Milton Keynes).flac",
    "01. Jiri Barta - 6 Cello Suites, No. 1 in G Major, BWV 1007 I. Prélude.flac",
    "14. John Williams - Setting the Trap (From Home Alone Soundtrack) (Instrumental).flac",
    "15. Kool Keith - Party In The Morgue (Club Mix).flac",
    "01. L'Orchestra Cinematique - Wednesday - Paint it Black (Epic Version).flac",
    "01. Linkin Park - Lost.flac",
    "01. LiSA - ReawakeR.flac",
    "31. Madonna - Beautiful Stranger (Album Version).flac",
    "04. Madonna - American Pie (Album Version).flac",
    "01. Metric - Black Sheep.flac",
    "18. John Mills - Mane on Ends (From Marvel Studios' Werewolf By NightScore).flac",
    "01 - Into The Badlands Theme.flac",
    "01. Old Jim - Kids.flac",
    "04. Panic! At The Disco - High Hopes.flac",
    "01. Panic! At The Disco - Say Amen (Saturday Night).flac",
    "10. Papa Roach - Leave a Light On (Talk Away The Dark).flac",
    "02. Plastikman - Runner.flac",
    "01. PLÜM - Stay.flac",
    "01. Rag'n'Bone Man - Human.flac",
    "01. Ritviz - Udd Gaye.flac",
    "05. Santana - Smooth.flac",
    "05. SAYGRACE - You Don't Own Me.flac",
    "12 - Shiro Sagisu - Nothing Can Be Explained (Vocal Version).flac",
    "21 - Shiro Sagisu - Number One (Vocal Version).flac",
    "21. Shiro Sagisu - Number One (Vocal Version).flac",
    "23 - Shiro Sagisu - Number One (Nas-T Mix).flac",
    "04 - Shiro Sagisu - Clavar La Espada.flac",
    "04. Shiro Sagisu - Clavar La Espada.flac",
    "07. Sum 41 - In Too Deep.flac",
    "01. The Babystars - ヒカリへ.flac",
    "02. The Crystal Method - Born Too Slow.flac",
    "09. The Who - Won't Get Fooled Again (Original Album Version).flac",
    "01. The xx - Intro.flac",
    "02. Timbaland - Give It To Me.flac",
    "06. Usher - Burn (Confession Special Edition Version).flac",
    "06. Usher - Caught Up.flac",
    "01. Jermaine Dupri - You Make Me Wanna.flac",
    "02. Various Interprets - Yeah!.flac",
    "02. will.i.am - I Gotta Feeling.flac",
    '02. John Travolta - Summer Nights (From "Grease" Soundtrack).flac',
    "02. Various Interprets - Cry Me a River.flac",
    "01. Various Interprets - I Believe.flac",
    "17. OneRepublic - Counting Stars.flac",
    "05. Various Interprets - Like I Love You.flac",
    "02. Various Interprets - Decepticons (Album Version).flac",
    "01. Various Interprets - Get Lucky (Radio Edit - feat. Pharrell Williams and Nile Rodgers).flac",
    "02. X Ambassadors - Renegades.flac",
    "01 - X Ambassadors - Renegades.flac",
    "01. Yeah Yeah Yeahs - Spitting Off the Edge of the World.flac",
    "17. Yu-Peng Chen - The Horizon.flac",
    "18. Yu-Peng Chen - Awaiting the Future.flac",
    "19. Yu-Peng Chen - Moonlit Wilderness.flac",
    "01. Yu-Peng Chen - Inazuma.flac",
    "24. Yu-Peng Chen - A Hollowed Skull.flac",
    "17. Yu-Peng Chen - Rex Incognito.flac",
    "05. TERRORBIRD - Run Me Out.flac",
}

# ── Script dir & reports ──────────────────────────────────────────────────────

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# ── Helpers ───────────────────────────────────────────────────────────────────

def confirm_prompt(n, action, dest_name):
    msg = input(f"{action} {n} item(s) to '{dest_name}'? (y/n): ").strip().lower()
    while msg not in ("y", "n"):
        msg = input("  Please enter y or n: ").strip().lower()
    if msg != "y":
        print("Aborted.")
        sys.exit(0)

def save_report(rows, suffix):
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_FOLDER / f"move_for_review_{suffix}_{timestamp}.csv"
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "status", "source", "dest", "error"])
        writer.writeheader()
        writer.writerows(rows)
    return report_path

# ── Undo mode ─────────────────────────────────────────────────────────────────

def run_undo():
    print("=" * 60)
    print("  move_for_review.py — v1.3  [UNDO MODE]")
    print(f"  Mode : {'DRY RUN — no files will be moved' if DRY_RUN else 'APPLY — files will be moved back'}")
    print("=" * 60)

    if not CSV_PATH:
        print("ERROR: --undo requires --csv <move_for_review_applied_csv>")
        sys.exit(1)

    csv_path = Path(CSV_PATH.strip('"'))
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    to_undo = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "moved":
                label = row.get("item") or row.get("filename", "")
                to_undo.append((label, row["source"], row["dest"]))

    print(f"\nItems to restore: {len(to_undo)}\n")
    for item, src, dst in to_undo:
        print(f"  {Path(dst).name}  →  {src}")

    if not to_undo:
        print("\nNothing to undo.")
        sys.exit(0)

    if not DRY_RUN:
        print()
        confirm_prompt(len(to_undo), "Restore", "original locations")

    rows   = []
    moved  = 0
    errors = 0

    for item, original_src, current_dest in to_undo:
        src_path  = Path(current_dest)
        dest_path = Path(original_src)

        if DRY_RUN:
            rows.append({"item": item, "status": "would_restore",
                         "source": str(src_path), "dest": str(dest_path), "error": ""})
        else:
            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_path), str(dest_path))
                rows.append({"item": item, "status": "restored",
                             "source": str(src_path), "dest": str(dest_path), "error": ""})
                moved += 1
            except Exception as e:
                rows.append({"item": item, "status": "error",
                             "source": str(src_path), "dest": str(dest_path), "error": str(e)})
                print(f"  ERROR: {e}")
                errors += 1

    report_path = save_report(rows, "undo_dry" if DRY_RUN else "undo_applied")
    print()
    if DRY_RUN:
        print(f"DRY RUN — {len(to_undo)} items would be restored. Run with --apply to execute.")
    else:
        print(f"Done — {moved} restored, {errors} errors.")
    print(f"Report: {report_path}")

# ── Move mode ─────────────────────────────────────────────────────────────────

def run_move():
    print("=" * 60)
    print("  move_for_review.py — v1.3")
    print(f"  Mode : {'DRY RUN — no folders will be moved' if DRY_RUN else 'APPLY — folders will be moved'}")
    print("=" * 60)

    if not CSV_PATH:
        print("ERROR: --csv <path> required")
        sys.exit(1)
    if not SOURCE_DIR:
        print("ERROR: --source <path> required")
        sys.exit(1)
    if not DEST_DIR:
        print("ERROR: --dest <path> required")
        sys.exit(1)

    csv_path   = Path(CSV_PATH.strip('"'))
    source_dir = Path(SOURCE_DIR.strip('"'))
    dest_dir   = Path(DEST_DIR.strip('"'))

    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"ERROR: Source folder not found: {source_dir}")
        sys.exit(1)

    target_files = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn     = row["filename"]
            status = row["status"]
            if status == "no_match":
                target_files[fn] = "no_match"
            elif fn in BAD_FINGERPRINT_FILES:
                target_files[fn] = "bad_fingerprint"

    print(f"\nScanning: {source_dir} ...")
    name_index = {}
    for p in source_dir.rglob("*"):
        if p.is_file():
            name_index[p.name] = p
    print(f"  {len(name_index)} files indexed.\n")

    album_folders = {}
    not_found     = []

    for fn, reason in target_files.items():
        file_path = name_index.get(fn)
        if not file_path:
            not_found.append((fn, reason))
            continue
        album_folder = file_path.parent
        album_folders[album_folder] = reason

    print(f"Album folders to move  : {len(album_folders)}")
    print(f"  no_match folders     : {sum(1 for r in album_folders.values() if r == 'no_match')}")
    print(f"  bad_fingerprint      : {sum(1 for r in album_folders.values() if r == 'bad_fingerprint')}")
    if not_found:
        print(f"Files not found (skipped): {len(not_found)}")
        for fn, reason in not_found:
            print(f"  [{reason}] {fn}")

    if not album_folders:
        print("\nNothing to move. Exiting.")
        sys.exit(0)

    print(f"\nDestination: {dest_dir}")
    print()

    moves = []
    for album_folder, reason in sorted(album_folders.items()):
        try:
            rel = album_folder.relative_to(source_dir)
        except ValueError:
            rel = Path(album_folder.name)
        dest_folder = dest_dir / rel
        moves.append((album_folder, dest_folder, reason))
        print(f"  [{reason:16s}] {rel}")

    if not DRY_RUN:
        print()
        confirm_prompt(len(moves), "Move", dest_dir.name)

    rows   = []
    moved  = 0
    errors = 0

    dest_dir.mkdir(parents=True, exist_ok=True)

    for src_folder, dst_folder, reason in moves:
        rel = str(src_folder.relative_to(source_dir))
        if DRY_RUN:
            rows.append({"item": rel, "status": "would_move",
                         "source": str(src_folder), "dest": str(dst_folder), "error": ""})
        else:
            try:
                dst_folder.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_folder), str(dst_folder))
                rows.append({"item": rel, "status": "moved",
                             "source": str(src_folder), "dest": str(dst_folder), "error": ""})
                moved += 1
            except Exception as e:
                rows.append({"item": rel, "status": "error",
                             "source": str(src_folder), "dest": str(dst_folder), "error": str(e)})
                print(f"  ERROR moving {rel}: {e}")
                errors += 1

    report_path = save_report(rows, "dry" if DRY_RUN else "applied")
    print()
    if DRY_RUN:
        print(f"DRY RUN — {len(moves)} folders would be moved. Run with --apply to execute.")
    else:
        print(f"Done — {moved} moved, {errors} errors.")
    print(f"Report: {report_path}")

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if UNDO_MODE:
        run_undo()
    else:
        run_move()
