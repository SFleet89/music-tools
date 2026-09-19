"""
check_cache_bitdepth.py
Quick diagnostic — checks how many rows in music_cache.db have
bit_depth and sample_rate populated.

Run from anywhere:
    python diagnostics/check_cache_bitdepth.py
"""
import sqlite3
from pathlib import Path

# music_cache.db lives at the project root, one level up from diagnostics/
DB = Path(__file__).resolve().parent.parent / "music_cache.db"

if not DB.exists():
    print(f"ERROR: DB not found at {DB}")
    raise SystemExit(1)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

total = conn.execute("SELECT COUNT(*) FROM metadata_cache").fetchone()[0]
if total == 0:
    print("metadata_cache is empty — run Build FP Cache first.")
    raise SystemExit(0)

nulls = conn.execute("""
    SELECT
        SUM(CASE WHEN bit_depth   IS NULL THEN 1 ELSE 0 END) AS null_bd,
        SUM(CASE WHEN sample_rate IS NULL THEN 1 ELSE 0 END) AS null_sr,
        SUM(CASE WHEN bitrate     IS NULL THEN 1 ELSE 0 END) AS null_br
    FROM metadata_cache
""").fetchone()

print(f"\nTotal rows       : {total:,}")
print(f"NULL bit_depth   : {nulls['null_bd']:,}  ({nulls['null_bd']/total*100:.1f}%)")
print(f"NULL sample_rate : {nulls['null_sr']:,}  ({nulls['null_sr']/total*100:.1f}%)")
print(f"NULL bitrate     : {nulls['null_br']:,}  ({nulls['null_br']/total*100:.1f}%)")

print("\nBit depth distribution:")
any_bd = False
for row in conn.execute("""
    SELECT bit_depth, COUNT(*) AS n
    FROM metadata_cache WHERE bit_depth IS NOT NULL
    GROUP BY bit_depth ORDER BY n DESC
"""):
    print(f"  {row['bit_depth']}-bit : {row['n']:,}")
    any_bd = True
if not any_bd:
    print("  (none — bit_depth is NULL for all rows)")

print("\nSample rate distribution:")
any_sr = False
for row in conn.execute("""
    SELECT sample_rate, COUNT(*) AS n
    FROM metadata_cache WHERE sample_rate IS NOT NULL
    GROUP BY sample_rate ORDER BY n DESC LIMIT 10
"""):
    print(f"  {row['sample_rate']:,} Hz : {row['n']:,}")
    any_sr = True
if not any_sr:
    print("  (none — sample_rate is NULL for all rows)")

print("\nFormats with NULL bit_depth (top 10):")
for row in conn.execute("""
    SELECT file_format, COUNT(*) AS n
    FROM metadata_cache WHERE bit_depth IS NULL
    GROUP BY file_format ORDER BY n DESC LIMIT 10
"""):
    print(f"  .{row['file_format'] or '(none)'} : {row['n']:,}")

conn.close()
print()
