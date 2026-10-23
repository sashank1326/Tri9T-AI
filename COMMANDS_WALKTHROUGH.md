# Medical Document QA & Traceability System — Complete Command Reference

> **Zero Placeholders:** Every command below contains real, working IDs from the database (`CardioTrack-Walkthrough`). You can copy and paste any command directly into your terminal without editing a single character!

---

## 0. Server Health Check

Verify that FastAPI, SQLite, MongoDB, and Tesseract OCR are healthy:

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

---

## Step 1: Ingestion & Structuring (Version 1)

Uploads `ct200_manual_v1.pdf`, parses the 6 pages into 50 nodes with parent-child links, and computes Merkle SHA-256 hashes:

```bash
curl -X POST "http://localhost:8000/api/v1/documents/ingest" \
  -F "document_id=CardioTrack-Walkthrough" \
  -F "title=CardioTrack CT-200 Blood Pressure Monitor Manual" \
  -F "version_name=v1" \
  -F "description=Official v1 Technical Manual" \
  -F "file=@data/ct200_manual_v1.pdf" | python3 -m json.tool
```

---

## Step 2: Document Versioning (Version 2 Ingestion)

Uploads `ct200_manual_v2.pdf` under the **exact same** `document_id=CardioTrack-Walkthrough` without overwriting `v1`:

```bash
curl -X POST "http://localhost:8000/api/v1/documents/ingest" \
  -F "document_id=CardioTrack-Walkthrough" \
  -F "title=CardioTrack CT-200 Blood Pressure Monitor Manual" \
  -F "version_name=v2" \
  -F "description=Official v2 Revised Manual" \
  -F "file=@data/ct200_manual_v2.pdf" | python3 -m json.tool
```

---

## Step 3: Browse API

### 3.1 List Top-Level Sections (Defaults to latest `v2`)
```bash
curl -s "http://localhost:8000/api/v1/documents/CardioTrack-Walkthrough/sections" | python3 -m json.tool | head -n 35
```

### 3.2 List Top-Level Sections for `v1`
```bash
curl -s "http://localhost:8000/api/v1/documents/CardioTrack-Walkthrough/sections?version=v1" | python3 -m json.tool | head -n 35
```

### 3.3 Snippet Search Across Document (`v1`)
Searches for `"battery"` across headings and paragraphs:
```bash
curl -s "http://localhost:8000/api/v1/documents/CardioTrack-Walkthrough/versions/v1/search?q=battery" | python3 -m json.tool
```

### 3.4 Fetch Full Details for the Battery Paragraph Node (Real ID: `fb1c37de-631c-41be-9443-e345c5a263ca`)
```bash
curl -s "http://localhost:8000/api/v1/documents/CardioTrack-Walkthrough/versions/v1/nodes/fb1c37de-631c-41be-9443-e345c5a263ca" | python3 -m json.tool
```

### 3.5 Single Node Diff Across Versions (Checks if Battery Node Changed in `v2`)
```bash
curl -s "http://localhost:8000/api/v1/documents/CardioTrack-Walkthrough/nodes/fb1c37de-631c-41be-9443-e345c5a263ca/diff" | python3 -m json.tool
```

---

## Step 4: Interactive Text Selection (Selection API)

### 4.1 Create a Version-Pinned Selection on the Battery Node
Freezes the `300 cycles` text with SHA-256 hash locked to `v1`:
```bash
curl -X POST "http://localhost:8000/api/v1/selections" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "CardioTrack-Walkthrough",
    "version_id": "v1",
    "node_ids": ["fb1c37de-631c-41be-9443-e345c5a263ca"],
    "title": "Battery Life Specification",
    "description": "Section 2.1.1.1 typical battery measurement cycles"
  }' | python3 -m json.tool
```

### 4.2 Retrieve the Selection (Real ID: `b017774f-9dfd-49f8-abc8-b465f340ea79`)
```bash
curl -s "http://localhost:8000/api/v1/selections/b017774f-9dfd-49f8-abc8-b465f340ea79" | python3 -m json.tool
```

---

## Step 5: AI Test-Case Generation (LLM Service)

Generates 4 medical QA test cases (`boundary`, `safety`, `performance`, `regulatory`) using the frozen selection:

```bash
curl -X POST "http://localhost:8000/api/v1/test-cases/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "selection_id": "b017774f-9dfd-49f8-abc8-b465f340ea79",
    "num_test_cases": 4
  }' | python3 -m json.tool
```

---

## Step 6: Retrieval & Staleness Detection (At Query Time)

### 6.1 Query Test Cases by Selection ID (Real ID: `b017774f-9dfd-49f8-abc8-b465f340ea79`)
```bash
curl -s "http://localhost:8000/api/v1/test-cases/by-selection/b017774f-9dfd-49f8-abc8-b465f340ea79" | python3 -m json.tool | tail -n 25
```

### 6.2 Query Test Cases by Node ID (Real ID: `fb1c37de-631c-41be-9443-e345c5a263ca`)
```bash
curl -s "http://localhost:8000/api/v1/test-cases/by-node/fb1c37de-631c-41be-9443-e345c5a263ca" | python3 -m json.tool | tail -n 25
```

### 6.3 Query Generation Batch with Staleness (Real ID: `55dd718b-e016-4bde-a665-998e74a780b4`)
```bash
curl -s "http://localhost:8000/api/v1/test-cases/by-generation/55dd718b-e016-4bde-a665-998e74a780b4" | python3 -m json.tool | tail -n 25
```

### 6.4 Query Individual Test Case `TC-004` (Real ID: `55dd718b-e016-4bde-a665-998e74a780b4_TC-004`)
```bash
curl -s "http://localhost:8000/api/v1/test-cases/55dd718b-e016-4bde-a665-998e74a780b4_TC-004" | python3 -m json.tool | tail -n 25
```

---

## Step 7: Document Version Diff API (Full Comparison)

Compare `v1` vs `v2` across all 50+ nodes with summary metrics and Git-style diffs:

```bash
curl -s "http://localhost:8000/api/v1/documents/CardioTrack-Walkthrough/compare?v1=v1&v2=v2" | python3 -m json.tool | head -n 45
```

---

## 🔍 Database Inspection Commands

### 1. SQLite Inspection (`data/medical_qa.db`)

```bash
# View all tables and their row counts:
sqlite3 data/medical_qa.db "SELECT 'documents' as tbl, count(*) as count FROM documents UNION ALL SELECT 'document_versions', count(*) FROM document_versions UNION ALL SELECT 'document_nodes', count(*) FROM document_nodes UNION ALL SELECT 'version_pinned_selections', count(*) FROM version_pinned_selections;"

# View all documents:
sqlite3 -header -column data/medical_qa.db "SELECT id, title FROM documents;"

# View versions:
sqlite3 -header -column data/medical_qa.db "SELECT version_name, page_count, root_hash FROM document_versions WHERE document_id='CardioTrack-Walkthrough';"

# View pinned selections:
sqlite3 -header -column data/medical_qa.db "SELECT id, title, document_id, content_hash FROM version_pinned_selections;"

# View top 5 heading nodes:
sqlite3 -header -column data/medical_qa.db "SELECT id, title, section_path, level FROM document_nodes WHERE node_type='heading' LIMIT 5;"
```

### 2. MongoDB Inspection (`medical_qa_system`)

```bash
# View collection counts in MongoDB:
.venv/bin/python3 -c "
from app.db.mongo import get_mongo_db
db = get_mongo_db()
for c in sorted(db.list_collection_names()):
    print(f'{c.ljust(20)}: {db[c].count_documents({})} documents')
"
```

---

## 🧪 Automated Unit Test Suite

Run the full pytest suite:

```bash
.venv/bin/pytest tests/test_parser.py -v
```
