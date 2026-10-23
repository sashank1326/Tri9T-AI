#!/usr/bin/env python3
"""
Seed script to populate SQLite and MongoDB with sample CT-200 medical manual versions,
version-pinned selections, and AI test cases.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.sqlite import init_db, SessionLocal
from app.db.models import DocumentNode
from app.services.document_service import DocumentService
from app.services.version_service import VersionService
from app.services.selection_service import SelectionService
from app.services.llm_service import LLMService
from app.services.staleness_service import StalenessService
from app.schemas.selection import SelectionCreateRequest
from tests.fixtures.pdf_generator import create_synthetic_pdf_v1, create_synthetic_pdf_v2


def main():
    print("=== Seeding Demo Medical QA & Traceability Data ===")
    os.makedirs("data", exist_ok=True)

    # 1. Generate synthetic PDF files
    v1_bytes = create_synthetic_pdf_v1()
    v2_bytes = create_synthetic_pdf_v2()

    v1_path = "data/CT-200_v1_demo.pdf"
    v2_path = "data/CT-200_v2_demo.pdf"

    with open(v1_path, "wb") as f:
        f.write(v1_bytes)
    with open(v2_path, "wb") as f:
        f.write(v2_bytes)
    print(f"Generated synthetic fixtures: {v1_path}, {v2_path}")

    # 2. Ingest v1 and v2
    init_db()
    db = SessionLocal()

    try:
        doc_svc = DocumentService(db)

        print("\n1. Ingesting Document 'CT-200-MANUAL' Version 'v1'...")
        res_v1 = doc_svc.ingest_pdf(
            document_id="CT-200-MANUAL",
            title="CT-200 Computed Tomography System Operator & Technical Manual",
            version_name="v1",
            file_bytes=v1_bytes,
            file_name="CT-200_v1.pdf",
            description="Initial system specification and radiation safety baseline."
        )
        print(f"   -> Version ID: {res_v1.id}, Pages: {res_v1.page_count}, Nodes: {res_v1.node_count}")

        print("\n2. Ingesting Document 'CT-200-MANUAL' Version 'v2'...")
        res_v2 = doc_svc.ingest_pdf(
            document_id="CT-200-MANUAL",
            title="CT-200 Computed Tomography System Operator & Technical Manual",
            version_name="v2",
            file_bytes=v2_bytes,
            file_name="CT-200_v2.pdf",
            description="Revised system specification with increased tube voltage and tightened emergency interlock."
        )
        print(f"   -> Version ID: {res_v2.id}, Pages: {res_v2.page_count}, Nodes: {res_v2.node_count}")

        # 3. Create Version-Pinned Selection on v1
        print("\n3. Creating Version-Pinned Selection on v1 Radiation Safety Section...")
        sel_svc = SelectionService(db)

        # Find radiation safety nodes in v1
        v1_nodes = db.query(DocumentNode).filter(
            DocumentNode.version_id == res_v1.id,
            DocumentNode.section_path.like("%radiation%") | DocumentNode.content.like("%tube voltage%")
        ).all()
        selected_node_ids = [n.id for n in v1_nodes]

        selection = sel_svc.create_selection(SelectionCreateRequest(
            document_id="CT-200-MANUAL",
            version_id=res_v1.id,
            node_ids=selected_node_ids,
            title="Radiation Generator & Interlock Safety Baseline",
            description="High voltage tube limits and emergency stop interlock protocol from v1 specification.",
            tags=["radiation", "safety", "interlock", "iec-60601"]
        ))
        print(f"   -> Created Selection ID: {selection.id}")
        print(f"   -> Pinned Content Hash:  {selection.content_hash}")

        # 4. Generate AI QA Test Cases
        print("\n4. Generating AI Test Cases from v1 Pinned Selection...")
        llm_svc = LLMService()
        batch = llm_svc.generate_test_cases(
            source_text=selection.pinned_content_snapshot,
            document_id="CT-200-MANUAL",
            source_version_id=res_v1.id,
            source_version_name="v1",
            selection_id=selection.id,
            node_ids=selection.node_ids,
            num_test_cases=4
        )
        print(f"   -> Generation Batch ID: {batch.generation_id}")
        print(f"   -> Generated {len(batch.test_cases)} QA Test Cases:")
        for tc in batch.test_cases:
            print(f"      [{tc.test_case_id}] {tc.title} ({tc.severity})")

        # 5. Check Staleness against v2
        print("\n5. Checking Staleness of v1 Test Cases Against Latest Document (v2)...")
        staleness_svc = StalenessService(db)
        staleness = staleness_svc.evaluate_staleness(
            document_id="CT-200-MANUAL",
            source_version_id=res_v1.id,
            source_hash=batch.source_hash,
            source_snapshot=batch.source_snapshot,
            node_ids=selection.node_ids,
            selection_id=selection.id
        )
        print(f"   -> Overall Status: {staleness.overall_status.value}")
        print(f"   -> Is Stale:        {staleness.is_stale}")
        print(f"   -> Diff Summary:   {staleness.diff_summary}")

        # 6. Version Diff Summary
        print("\n6. Comparing v1 vs v2 Full Document Diff...")
        ver_svc = VersionService(db)
        compare_res = ver_svc.compare_versions("CT-200-MANUAL", "v1", "v2")
        print(f"   -> Unchanged Nodes: {compare_res.summary.unchanged_count}")
        print(f"   -> Modified Nodes:  {compare_res.summary.modified_count}")
        print(f"   -> Added Nodes:     {compare_res.summary.added_count}")
        print(f"   -> Deleted Nodes:   {compare_res.summary.deleted_count}")

        print("\n=== Demo Data Seeding Completed Successfully! ===")

    finally:
        db.close()


if __name__ == "__main__":
    main()
