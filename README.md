# AI-Powered Medical Document QA and Traceability System
### Backend Project for Tri9T AI Engineering Internship Assignment

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-SQLAlchemy-003B57?style=flat&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-8.0+-47A248?style=flat&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-3.8%20Flash-8E75B2?style=flat&logo=google&logoColor=white)](https://ai.google.dev/)
[![Pytest](https://img.shields.io/badge/Pytest-18%20Passed-0A9EDC?style=flat&logo=pytest&logoColor=white)](https://pytest.org/)

---

## 1. Overview

The **AI-Powered Medical Document QA and Traceability System** is an enterprise-grade backend engineered to ingest, parse, version, and trace technical specifications and operating manuals for complex medical devices (such as the CT-200 computed tomography scanner).

The system enforces strict medical regulatory standards (**IEC 62304**, **ISO 13485**, and **FDA 21 CFR Part 820**) by providing:
- **Hierarchical PDF Parsing**: Automatic extraction of sections, headings, subsections, paragraphs, lists, tables, and figures with Tesseract OCR fallback for scanned pages.
- **Merkle Content Hashing**: Deterministic SHA-256 content hashes computed for every individual node and composite hashes for sections.
- **Document Versioning & Diffing**: Full version tracking (e.g. `v1` and `v2`) with node-by-node classification into `unchanged`, `modified`, `added`, and `deleted`, plus unified text diffs.
- **Version-Pinned Selections**: Immutable requirement selections that preserve exact text snapshots and content hashes when newer versions are ingested.
- **Gemini-Powered Test-Case Generation**: Automated generation of 3–5 rigorous QA test cases adhering to medical verification criteria, validated with Pydantic and persisted in MongoDB.
- **Dynamic Staleness Detection**: Real-time evaluation of test cases against the latest document version, flagging modified or deleted requirements with comprehensive diff summaries.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.11+ | Modern type annotations, async/await support |
| **Web Framework** | FastAPI + Uvicorn | High-performance RESTful API endpoints and automatic OpenAPI docs |
| **Validation** | Pydantic v2 + Pydantic-Settings | Strict schema validation, settings management, and Gemini response validation |
| **Relational DB** | SQLite + SQLAlchemy 2.0 | Document metadata, versions, hierarchical node tree, version-pinned selections |
| **Document DB** | MongoDB 8.0+ / PyMongo / Mongomock | AI test cases, full source snapshot blobs, and compliance audit logs |
| **PDF Extraction** | PyMuPDF (v2.0) | High-speed layout, font metrics, span analysis, and table detection |
| **OCR Fallback** | Tesseract OCR 5.5 + PyTesseract | Optical character recognition on rasterized/scanned manual pages |
| **AI Generation** | Google Gen AI SDK (`google-genai`) | AI test case generation with `gemini-3.8-flash` |
| **Testing** | Pytest + Pytest-Asyncio + HTTPX | 18 unit and end-to-end integration tests |

---

## 3. Architecture & Data Flow

```
                                  [ Medical PDF Manual ]
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │       Modular PDF Parser      │
                             │  (PyMuPDF + Tesseract OCR)    │
                             └───────────────┬───────────────┘
                                             │
                   ┌─────────────────────────┴─────────────────────────┐
                   ▼                                                   ▼
       ┌────────────────────────┐                          ┌────────────────────────┐
       │   Hierarchy Builder    │                          │   Content Hash Engine  │
       │  (Duplicate Resolver)  │                          │  (Leaf + Merkle Tree)  │
       └───────────┬────────────┘                          └───────────┬────────────┘
                   └─────────────────────────┬─────────────────────────┘
                                             ▼
                               ┌───────────────────────────┐
                               │     SQLAlchemy + SQLite   │
                               │  - Document & Versions    │
                               │  - Node Tree Hierarchy    │
                               │  - Pinned Selections      │
                               └─────────────┬─────────────┘
                                             │
                         ┌───────────────────┴───────────────────┐
                         ▼                                       ▼
             ┌───────────────────────┐               ┌───────────────────────┐
             │ Version Diff Engine   │               │ Gemini AI Generation  │
             │ (Unchanged, Modified, │               │  (3-5 QA Test Cases)  │
             │   Added, Deleted)     │               └───────────┬───────────┘
             └───────────────────────┘                           ▼
                                                     ┌───────────────────────┐
                                                     │        MongoDB        │
                                                     │  - QA Test Cases      │
                                                     │  - Source Snapshots   │
                                                     │  - Staleness Audits   │
                                                     └───────────┬───────────┘
                                                                 │
                                                                 ▼
                                                     ┌───────────────────────┐
                                                     │  Staleness Detector   │
                                                     │  (Source vs Latest)   │
                                                     └───────────────────────┘
```

---

## 4. Installation & Setup

### Prerequisites
- **Python**: Version 3.11+
- **MongoDB**: Version 6.0+ (running locally on port 27017 or remote URI)
- **Tesseract OCR**: Installed via Homebrew on macOS (`brew install tesseract`) or apt on Linux (`apt install tesseract-ocr`)

### Step 1: Clone and Set Up Virtual Environment

```bash
cd /path/to/project
python3.11 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` to configure your settings:
```ini
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000

SQLITE_DB_URL=sqlite:///./data/medical_qa.db
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=medical_qa_system

# Provide your Google Gemini API key for live AI test-case generation
# (Mock fallback is automatically used for unit tests or when omitted)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

OCR_ENABLED=true
TESSERACT_CMD=tesseract
```

---

## 5. Execution & Usage

### 1. Start MongoDB (if not already running)
```bash
mongod --dbpath data/db --fork --logpath data/mongod.log
```

### 2. Start the FastAPI Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Interactive ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### 3. Seed Demo Data (Automatic End-to-End Simulation)
To instantly generate synthetic v1 and v2 CT-200 PDFs, ingest both versions, create a pinned selection, generate AI test cases, and verify staleness:

```bash
python scripts/seed_demo_data.py
```

### 4. Ingest a PDF via Command-Line CLI
```bash
python scripts/ingest_pdf.py \
  --file data/CT-200_v1_demo.pdf \
  --doc-id CT-200-MANUAL \
  --version v1 \
  --title "CT-200 Technical Manual"
```

---

## 6. Running the Automated Test Suite

All features include unit and end-to-end integration tests using **Pytest**:

```bash
pytest -v
```

### Test Coverage Highlights:
- `tests/test_parser.py`: PDF layout extraction, hierarchy reconstruction, duplicate headings disambiguation, Merkle hash calculations, and OCR fallback.
- `tests/test_versioning.py`: v1 vs v2 node matching, classification (`unchanged`, `modified`, `added`, `deleted`), unified diff generation, and duplicate version rejection.
- `tests/test_selections.py`: Version-pinned selections, verifying immutable snapshot and hash retention across subsequent document uploads.
- `tests/test_llm_validation.py`: Pydantic validation of 3–5 test cases, boundary checks (<3, >5), missing field errors, markdown fence stripping, malformed JSON recovery, and MongoDB persistence.
- `tests/test_staleness.py`: Dynamic staleness detection across unchanged, modified, and deleted requirements.
- `tests/test_e2e_workflow.py`: Complete HTTP lifecycle test through FastAPI TestClient.

---

## 7. REST API Reference

### Document Ingestion & Browsing
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/documents/ingest` | Upload and ingest a PDF version with metadata |
| `GET` | `/api/v1/documents` | List all documents and their version summaries |
| `GET` | `/api/v1/documents/{document_id}` | Retrieve document details and versions |
| `GET` | `/api/v1/documents/{document_id}/versions/{version_id}/sections` | List table of contents / root headings |
| `GET` | `/api/v1/documents/{document_id}/versions/{version_id}/tree` | Get full recursive document hierarchy tree |
| `GET` | `/api/v1/documents/{document_id}/versions/{version_id}/nodes/{node_id}` | Retrieve specific node with metadata and hash |
| `GET` | `/api/v1/documents/{document_id}/versions/{version_id}/search?q={query}` | Full-text search with snippet highlighting |
| `GET` | `/api/v1/documents/{document_id}/compare?v1={v1}&v2={v2}` | Compare two versions with diff summary & node diffs |

### Version-Pinned Selections
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/selections` | Pin selected document nodes with immutable text snapshot and hash |
| `GET` | `/api/v1/selections/{selection_id}` | Retrieve pinned selection by ID |
| `GET` | `/api/v1/selections` | List selections (optionally filtered by `document_id`) |

### AI Test-Case Generation & Staleness Retrieval
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/test-cases/generate` | Generate 3–5 validated QA test cases via Gemini and persist to MongoDB |
| `GET` | `/api/v1/test-cases/by-selection/{selection_id}` | Retrieve test cases for a selection with live staleness report |
| `GET` | `/api/v1/test-cases/by-node/{node_id}` | Retrieve test cases covering a specific document node |
| `GET` | `/api/v1/test-cases/by-generation/{generation_id}` | Retrieve generation batch by ID with source snapshot & staleness |
| `GET` | `/api/v1/test-cases/{test_case_id}` | Retrieve individual test case with staleness status |
| `GET` | `/api/v1/health` | System health check (SQLite, MongoDB, Tesseract) |

---

## 8. Regulatory Compliance Context

In medical device software lifecycle management (**IEC 62304**):
1. **Requirements Traceability**: Test cases must have bidirectional traceability to specific system requirements. The system maintains direct foreign keys and quotes linking each generated test case to its source section path and node IDs.
2. **Change Control**: When manual specifications change in v2 (e.g. tube voltage or emergency stop timing), verification test cases linked to outdated parameters can lead to safety test false-positives. The **Staleness Detector** identifies exact requirement changes, flags obsolete tests as `STALE_MODIFIED` or `STALE_DELETED`, and logs an audit trail in MongoDB.
