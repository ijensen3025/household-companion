#!/usr/bin/env python3
"""READ-ONLY: compare the current Google Sheet to the completed Firestore import.

Uses the existing household-firestore-migration/migrate.py schema and service
account impersonation. Never writes to Firestore or Google Sheets.
"""
import argparse
import importlib.util
from pathlib import Path
import sys
from google.cloud import firestore

PROJECT = "household-chore-tracker-514819"
DATABASE = "household-tracker"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--migration-dir", required=True, help="Folder containing migrate.py")
    args = p.parse_args()
    path = Path(args.migration_dir).expanduser().resolve() / "migrate.py"
    if not path.is_file():
        p.error(f"No migrate.py at {path}")
    spec = importlib.util.spec_from_file_location("original_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sheets = migration.read_google_sheet()
    desired, errors = migration.sheet_payload(sheets)
    if errors:
        for error in errors: print("INVALID SOURCE:", error)
        return 2
    db = firestore.Client(project=PROJECT, database=DATABASE)
    marker = db.collection("migration_metadata").document("initial_google_sheets_v1").get()
    if not marker.exists:
        print("FAILED: verified migration marker missing")
        return 2
    original_hash = marker.to_dict().get("source_sha256")
    current_hash = migration.fingerprint(sheets)
    if original_hash != current_hash:
        print("CUTOVER BLOCKED: Google Sheet has changed since the migration.")
        print("Do not deploy v2 until the differences are reconciled.")
        return 2
    for collection in ("chores", "completions", "family_events"):
        docs = {d.id: d.to_dict() for d in db.collection(collection).stream()}
        if docs != desired[collection]:
            print(f"CUTOVER BLOCKED: mismatch in {collection}. Expected {len(desired[collection])}, found {len(docs)}")
            return 2
        print(f"Verified {collection}: {len(docs)} records")
    print("CUTOVER VERIFIED — exact snapshot comparison and migration marker passed.")
    print("Freeze Google Sheets writes before switching Cloud Run to v2.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
