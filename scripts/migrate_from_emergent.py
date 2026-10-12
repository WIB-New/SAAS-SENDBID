"""
StorageHub — Migration script: Emergent Object Storage → Local Storage
Usage:
    python scripts/migrate_from_emergent.py \
        --emergent-base-url https://storage.emergent.example.com \
        --emergent-api-key YOUR_KEY \
        --storage-url http://localhost:8080 \
        --storage-api-key dev-api-key \
        --dry-run

The script downloads each file from Emergent, verifies its checksum,
re-uploads to the local storage service, and logs results.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── CLI arguments
parser = argparse.ArgumentParser(description="Migrate files from Emergent Storage to STORAGEHUB Storage")
parser.add_argument("--emergent-base-url", required=True, help="Emergent Storage base URL")
parser.add_argument("--emergent-api-key", required=True, help="Emergent API key")
parser.add_argument("--storage-url", default="http://localhost:8080", help="STORAGEHUB storage service URL")
parser.add_argument("--storage-api-key", default="dev-api-key", help="STORAGEHUB API key")
parser.add_argument("--manifest", help="CSV manifest file with file list (id,category,owner_user_id,url)")
parser.add_argument("--dry-run", action="store_true", help="Simulate without uploading")
parser.add_argument("--output-report", default="migration_report.json", help="Output report file")
parser.add_argument("--batch-size", type=int, default=10, help="Files per batch")
parser.add_argument("--delay-seconds", type=float, default=0.5, help="Delay between files")


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_from_emergent(url: str, api_key: str) -> bytes:
    resp = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    resp.raise_for_status()
    return resp.content


def upload_to_storagehub(
    storage_url: str,
    api_key: str,
    content: bytes,
    filename: str,
    mime_type: str,
    category: str,
    owner_user_id: str,
) -> dict:
    files = {"file": (filename, content, mime_type)}
    data = {"category": category, "owner_user_id": owner_user_id}
    headers = {"X-API-Key": api_key, "X-User-Id": "migration-script", "X-User-Role": "admin"}
    resp = requests.post(
        f"{storage_url}/v1/files",
        files=files,
        data=data,
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def migrate(args):
    if not args.manifest:
        print("ERROR: --manifest is required. Provide a CSV with columns: id,category,owner_user_id,url,checksum")
        sys.exit(1)

    report = {
        "started_at": datetime.utcnow().isoformat(),
        "dry_run": args.dry_run,
        "success": [],
        "failed": [],
        "skipped": [],
    }

    with open(args.manifest, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[MIGRATION] Found {len(rows)} files to migrate")
    if args.dry_run:
        print("[MIGRATION] DRY RUN — no files will be uploaded")

    for i, row in enumerate(rows, 1):
        file_id = row.get("id", f"file_{i}")
        category = row.get("category", "avatars")
        owner = row.get("owner_user_id", "unknown")
        url = row.get("url", "")
        expected_checksum = row.get("checksum", "")

        print(f"[{i}/{len(rows)}] Migrating {file_id} ({category}) — owner={owner}")

        try:
            # Download
            content = download_from_emergent(url, args.emergent_api_key)
            actual_checksum = sha256_of_bytes(content)

            # Checksum verification
            if expected_checksum and actual_checksum != expected_checksum:
                print(f"  WARNING: Checksum mismatch for {file_id}")
                report["failed"].append({
                    "id": file_id,
                    "error": f"Checksum mismatch: expected={expected_checksum}, got={actual_checksum}",
                })
                continue

            print(f"  Downloaded: {len(content)} bytes, checksum={actual_checksum[:16]}...")

            if not args.dry_run:
                # Upload to STORAGEHUB
                result = upload_to_storagehub(
                    storage_url=args.storage_url,
                    api_key=args.storage_api_key,
                    content=content,
                    filename=f"{file_id}",
                    mime_type=_guess_mime(content),
                    category=category,
                    owner_user_id=owner,
                )
                print(f"  Uploaded: new_id={result.get('file_id')}")
                report["success"].append({
                    "original_id": file_id,
                    "new_id": result.get("file_id"),
                    "checksum": actual_checksum,
                    "size": len(content),
                })
            else:
                print(f"  [DRY RUN] Would upload {len(content)} bytes")
                report["success"].append({"original_id": file_id, "dry_run": True})

            time.sleep(args.delay_seconds)

        except requests.HTTPError as e:
            print(f"  ERROR: HTTP {e.response.status_code} — {e}")
            report["failed"].append({"id": file_id, "error": str(e)})
        except Exception as e:
            print(f"  ERROR: {e}")
            report["failed"].append({"id": file_id, "error": str(e)})

    # Write report
    report["finished_at"] = datetime.utcnow().isoformat()
    report["total"] = len(rows)
    report["success_count"] = len(report["success"])
    report["failed_count"] = len(report["failed"])

    with open(args.output_report, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[MIGRATION] Done. Success: {report['success_count']}, Failed: {report['failed_count']}")
    print(f"[MIGRATION] Report: {args.output_report}")


def _guess_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"%PDF":
        return "application/pdf"
    return "application/octet-stream"


if __name__ == "__main__":
    args = parser.parse_args()
    migrate(args)
