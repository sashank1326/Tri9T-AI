#!/usr/bin/env python3
"""
CLI script to ingest a PDF manual into the Medical QA & Traceability System.
Usage:
    python scripts/ingest_pdf.py --file sample.pdf --doc-id CT-200 --version v1 --title "CT-200 Manual"
"""
import argparse
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.sqlite import init_db, SessionLocal
from app.services.document_service import DocumentService


def main():
    parser = argparse.ArgumentParser(description="Ingest a PDF manual into the QA & Traceability System")
    parser.add_argument("--file", "-f", required=True, help="Path to PDF file")
    parser.add_argument("--doc-id", "-d", required=True, help="Unique document identifier (e.g., CT-200-MANUAL)")
    parser.add_argument("--version", "-v", required=True, help="Version string (e.g., v1, v2)")
    parser.add_argument("--title", "-t", default=None, help="Document title")
    parser.add_argument("--desc", default=None, help="Document description")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading PDF file: {args.file}...")
    with open(args.file, "rb") as f:
        file_bytes = f.read()

    # Ensure DB tables exist
    init_db()
    db = SessionLocal()

    try:
        service = DocumentService(db)
        title = args.title or os.path.splitext(os.path.basename(args.file))[0]
        file_name = os.path.basename(args.file)

        print(f"Ingesting Document '{args.doc_id}' Version '{args.version}'...")
        res = service.ingest_pdf(
            document_id=args.doc_id,
            title=title,
            version_name=args.version,
            file_bytes=file_bytes,
            file_name=file_name,
            description=args.desc
        )

        print("\n=== Ingestion Successful ===")
        print(f"Document ID:   {res.document_id}")
        print(f"Version Name:  {res.version_name}")
        print(f"Pages Extracted: {res.page_count}")
        print(f"Nodes Created:   {res.node_count}")
        print(f"File Hash:     {res.file_hash}")
        print(f"Root Hash:     {res.root_hash}")
        print(f"Created At:    {res.created_at}")

    except Exception as e:
        print(f"\nIngestion Failed: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
