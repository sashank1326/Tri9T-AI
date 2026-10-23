import io
import pytest


def test_complete_end_to_end_workflow(client, pdf_v1_bytes, pdf_v2_bytes):
    """
    End-to-end integration test validating the entire medical document QA
    and traceability lifecycle via HTTP API endpoints:
    1. Ingest v1 PDF
    2. Browse sections and tree
    3. Search requirements
    4. Save version-pinned selection
    5. Generate AI QA test cases
    6. Verify initial status is UP_TO_DATE
    7. Ingest v2 PDF
    8. Verify old selection retains original v1 text (immutability)
    9. Verify test case retrieval detects staleness (STALE_MODIFIED)
    10. Compare versions diff
    """
    # 1. Ingest v1
    response_v1 = client.post(
        "/api/v1/documents/ingest",
        data={
            "document_id": "CT-200-E2E",
            "title": "CT-200 Computed Tomography System Manual",
            "version_name": "v1",
            "description": "Baseline v1 specification"
        },
        files={"file": ("CT-200_v1.pdf", io.BytesIO(pdf_v1_bytes), "application/pdf")}
    )
    assert response_v1.status_code == 201
    v1_data = response_v1.json()
    v1_id = v1_data["id"]
    assert v1_data["version_name"] == "v1"
    assert v1_data["node_count"] > 0

    # 2. Browse sections & tree
    sections_resp = client.get(f"/api/v1/documents/CT-200-E2E/versions/{v1_id}/sections")
    assert sections_resp.status_code == 200
    sections = sections_resp.json()
    assert len(sections) > 0

    tree_resp = client.get(f"/api/v1/documents/CT-200-E2E/versions/{v1_id}/tree")
    assert tree_resp.status_code == 200
    tree = tree_resp.json()
    assert len(tree) > 0

    # 3. Search document for "120 kV"
    search_resp = client.get(f"/api/v1/documents/CT-200-E2E/versions/{v1_id}/search?q=120+kV")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total_matches"] >= 1
    target_node = search_data["results"][0]
    target_node_id = target_node["node_id"]

    # 4. Save Version-Pinned Selection
    sel_resp = client.post(
        "/api/v1/selections",
        json={
            "document_id": "CT-200-E2E",
            "version_id": v1_id,
            "node_ids": [target_node_id],
            "title": "Radiation Voltage Limit Selection",
            "description": "Baseline generator voltage limit for safety audit",
            "tags": ["safety", "generator"]
        }
    )
    assert sel_resp.status_code == 201
    selection = sel_resp.json()
    selection_id = selection["id"]
    original_snapshot = selection["pinned_content_snapshot"]
    original_hash = selection["content_hash"]
    assert "120 kV" in original_snapshot

    # 5. Generate AI QA test cases
    gen_resp = client.post(
        "/api/v1/test-cases/generate",
        json={
            "selection_id": selection_id,
            "num_test_cases": 4
        }
    )
    assert gen_resp.status_code == 201
    gen_data = gen_resp.json()
    assert len(gen_data["test_cases"]) == 4
    generation_id = gen_data["generation_id"]

    # 6. Verify initial staleness against v1 (UP_TO_DATE)
    assert gen_data["staleness"]["overall_status"] == "UP_TO_DATE"
    assert gen_data["staleness"]["is_stale"] is False

    # 7. Ingest v2 PDF (voltage changed to 140 kV, latency to 15 ms, pediatric added)
    response_v2 = client.post(
        "/api/v1/documents/ingest",
        data={
            "document_id": "CT-200-E2E",
            "title": "CT-200 Computed Tomography System Manual",
            "version_name": "v2",
            "description": "Revised v2 specification"
        },
        files={"file": ("CT-200_v2.pdf", io.BytesIO(pdf_v2_bytes), "application/pdf")}
    )
    assert response_v2.status_code == 201
    v2_data = response_v2.json()
    assert v2_data["version_name"] == "v2"

    # 8. Verify old selection retains original v1 text (IMMUTABILITY)
    get_sel_resp = client.get(f"/api/v1/selections/{selection_id}")
    assert get_sel_resp.status_code == 200
    retrieved_sel = get_sel_resp.json()
    assert retrieved_sel["version_id"] == v1_id
    assert retrieved_sel["pinned_content_snapshot"] == original_snapshot
    assert retrieved_sel["content_hash"] == original_hash
    assert "120 kV" in retrieved_sel["pinned_content_snapshot"]
    assert "140 kV" not in retrieved_sel["pinned_content_snapshot"]

    # 9. Retrieve test cases and verify STALENESS is detected against v2
    tc_retrieval_resp = client.get(f"/api/v1/test-cases/by-selection/{selection_id}")
    assert tc_retrieval_resp.status_code == 200
    batches = tc_retrieval_resp.json()
    assert len(batches) >= 1
    current_batch = batches[0]

    assert current_batch["staleness"] is not None
    assert current_batch["staleness"]["is_stale"] is True
    assert current_batch["staleness"]["overall_status"] == "STALE_MODIFIED"
    assert current_batch["staleness"]["diff_summary"] is not None

    # Retrieve individual test case
    tc_id = current_batch["test_cases"][0]["test_case_id"]
    tc_single_resp = client.get(f"/api/v1/test-cases/{tc_id}")
    assert tc_single_resp.status_code == 200
    tc_single = tc_single_resp.json()
    assert tc_single["staleness"]["overall_status"] == "STALE_MODIFIED"

    # 10. Compare versions diff endpoint
    compare_resp = client.get("/api/v1/documents/CT-200-E2E/compare?v1=v1&v2=v2")
    assert compare_resp.status_code == 200
    comp_data = compare_resp.json()
    assert comp_data["summary"]["modified_count"] > 0
    assert comp_data["summary"]["added_count"] > 0

    # 11. Health endpoint
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"
