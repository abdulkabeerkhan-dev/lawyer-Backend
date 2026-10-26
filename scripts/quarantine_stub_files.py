import os
import shutil

REPO_DIR = r"I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
QUARANTINE_DIR = os.path.join(REPO_DIR, "data", "quarantine")

ACTS_10 = {
    "BCO_1962",
    "BANKING_COMPANIES_1962",
    "CONTRACT_1872",
    "CPC_1908",
    "CRPC_1898",
    "FIO_2001",
    "LIMITATION_1908",
    "PPC_1860",
    "REGISTRATION_1908",
    "STAMP_1899",
    "STAMP_ACT_1899",
    "TPA_1882"
}

def move_stubs_for_folder(subfolder_name: str):
    src_dir = os.path.join(REPO_DIR, "data", subfolder_name)
    dst_dir = os.path.join(QUARANTINE_DIR, subfolder_name)
    os.makedirs(dst_dir, exist_ok=True)

    if not os.path.exists(src_dir):
        return

    moved_count = 0
    kept_count = 0
    for fname in os.listdir(src_dir):
        p = os.path.join(src_dir, fname)
        if not os.path.isfile(p):
            continue

        # Check if file belongs to the 10 authentic acts
        should_keep = any(fname.startswith(act) for act in ACTS_10)
        if should_keep:
            kept_count += 1
        else:
            dst_path = os.path.join(dst_dir, fname)
            shutil.move(p, dst_path)
            moved_count += 1

    print(f"[{subfolder_name}] Kept: {kept_count} authentic files, Moved: {moved_count} stub files to {dst_dir}")

def main():
    print("=" * 80)
    print("QUARANTINING ALL UNSOURCED STUB STATUTE FILES")
    print("=" * 80)
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    move_stubs_for_folder("unified_statutes")
    move_stubs_for_folder("statute_tables")
    move_stubs_for_folder("statute_versions")
    print("Quarantine completed successfully.")

if __name__ == "__main__":
    main()
