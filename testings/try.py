"""
Manual smoke-test / demo script for Siftout.
Run from the SIFTOUT root:  python testings/try.py
"""

from siftout import Janitor

# ── Clean ─────────────────────────────────────────────────────────────────────
print("=" * 60)
print("  Siftout — workspace cleaner demo")
print("=" * 60)

cleaner = Janitor(extra_patterns=["*.bak"], dry_run=True)

print("\n[1] Listing trash (dry-run):")
trash = cleaner.list_trash()
for item in trash:
    print(f"    {item}")

print("\n[2] Running self_destruct (dry-run — nothing deleted):")
report = cleaner.self_destruct()
print(f"    Report: {report}")

# ── Secure ────────────────────────────────────────────────────────────────────
print("\n[3] Scanning for secrets (dry-run):")
secure_report = cleaner.secure_env()
print(f"    Secure report: {secure_report}")

# ── Duplicates ────────────────────────────────────────────────────────────────
print("\n[4] Scanning for duplicate files:")
dupes = cleaner.scan_duplicates()
if dupes:
    for h, paths in dupes.items():
        print(f"    [{h[:12]}…] {[str(p) for p in paths]}")
else:
    print("    No duplicates found.")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[5] Workspace summary:")
data = cleaner.summary()
for k, v in data.items():
    print(f"    {k:<25} {v}")

print("\nDone ✅")