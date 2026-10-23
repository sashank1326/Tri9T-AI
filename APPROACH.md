# System Design & Implementation Approach

## AI-Powered Medical Document QA and Traceability System
### Technical Architecture, Design Choices, Trade-offs, and Limitations

---

## 1. Architectural Strategy & Dual-Database Design

A core engineering decision in this system is the **polyglot persistence model** combining **SQLite (via SQLAlchemy 2.0)** with **MongoDB (via PyMongo / Mongomock)**.

```
                    ┌────────────────────────────────────────────────────────┐
                    │               FastAPI Application Layer               │
                    └───────────┬────────────────────────────────┬───────────┘
                                │                                │
                                ▼                                ▼
              ┌───────────────────────────────────┐    ┌───────────────────────────────────┐
              │         SQLite + SQLAlchemy       │    │              MongoDB              │
              ├───────────────────────────────────┤    ├───────────────────────────────────┤
              │ • Documents & Version Metadata    │    │ • Generated AI QA Test Cases      │
              │ • Hierarchical Document Node Tree │    │ • Immutable Source Snapshots      │
              │ • Self-referential Parent-Child   │    │ • Prompt & Raw LLM Traces         │
              │ • Version-Pinned Selections       │    │ • Historical Staleness Audits     │
              │ • Merkle Content Hashes (SHA-256) │    │ • Compliance Traceability Logs    │
              └───────────────────────────────────┘    └───────────────────────────────────┘
```

### Why SQLite for Document Structure?
1. **Relational Tree Integrity**: Document hierarchies are recursive trees (Document -> Sections -> Subsections -> Paragraphs/Tables). Relational foreign keys with `ON DELETE CASCADE` and self-referential relationships (`DocumentNode.parent_id -> DocumentNode.id`) ensure referential integrity.
2. **ACID Transactions**: Ingesting a PDF version requires inserting hundreds of nodes atomically. If any node fails or an error occurs during hierarchy reconstruction, the transaction cleanly rolls back.
3. **Deterministic Querying**: Ordering nodes by `order_index` and querying specific sub-trees by `section_path` index is fast and index-backed in SQLite.

### Why MongoDB for AI Test Cases & Snapshots?
1. **Semi-Structured Test Cases**: Medical test cases vary across categories (`safety`, `boundary`, `functional`, `performance`, `regulatory`) and may contain variable precondition arrays, multi-step actions, and nested traceability metadata. Document storage accommodates this cleanly without sparse relational tables.
2. **Immutable Source Snapshots**: In medical compliance (FDA 21 CFR Part 820 / IEC 62304), auditability requires storing the exact, unabridged text snapshot provided to the LLM at the time of generation. MongoDB stores these snapshots alongside the generated test cases as persistent audit records.
3. **Test Isolation with Mongomock**: During automated CI/CD testing, `mongomock` provides an in-memory document store with zero external service dependencies, while production runs on real MongoDB.

---

## 2. Modular PDF Parser & Layout Analysis Engine

The ingestion pipeline (`app/services/pdf_parser/`) is strictly decoupled into modular components so that document-specific heuristics (e.g. for the CT-200 manual) can be tuned without altering storage, diffing, or AI generation services.

### A. Font Statistics & Heading Detection
Rather than relying on hardcoded font sizes (which break across different manufacturer manuals), the parser executes an initial pass over the document:
1. Calculates character frequency histograms across all text spans to dynamically determine the **predominant body font size** (e.g., 10pt).
2. Classifies text blocks as headings using two complementary mechanisms:
   - **Structured Section Numbering**: Matches regular expressions such as `^(\d+(\.\d+)*)\s+(.*)$` (e.g., `1. Overview`, `2.1 Safety Protocol`, `2.1.2 Interlock Delay`). The heading depth level is directly derived from dot count.
   - **Relative Font Scaling & Weight**: If numbering is absent, blocks with font sizes $\ge 1.15 \times \text{body font size}$ or short bold lines (< 140 chars) are classified as headings, mapping font scale to levels (1, 2, 3).

### B. Table & Figure Extraction
- **Tables**: Extracted using PyMuPDF's table detection (`page.find_tables()`). Cell matrices are transformed into Markdown tables (`| Col1 | Col2 |`) with preserved column headers and bounding boxes. Table bounding boxes are recorded to prevent cell text from being duplicated as standard paragraphs.
- **Figures & Captions**: Image references (`page.get_images()`) are tracked along with bounding boxes. Proximity search immediately below each image rect captures figure titles and captions (e.g. `Figure 1: Gantry Schematic`).

### C. Optical Character Recognition (OCR) Fallback
Scanned manuals or diagram-heavy pages frequently contain zero embedded text fonts. The `OCROptimizer` checks whether a page contains extractable text:
- If a page has minimal or zero native text, it automatically renders a high-resolution pixmap (200 DPI) and invokes `pytesseract` to perform character recognition.
- OCR text is parsed into structured paragraphs and headings, ensuring zero silent content loss.

---

## 3. Hierarchy Reconstruction & Duplicate Headings Resolution

### The Duplicate Headings Problem
Technical manuals frequently reuse identical section titles across different modules. For example:
- `Chapter 3 (Hardware Subsystems)` $\rightarrow$ `Warnings and Precautions`
- `Chapter 4 (Software Subsystems)` $\rightarrow$ `Warnings and Precautions`

If node identity or paths were simply `/warnings-and-precautions`, cross-version alignment would collide and corrupt requirement traceability.

### Disambiguation Algorithm
The `HierarchyReconstructor` maintains an active heading stack and builds hierarchical semantic paths:
1. For each node, its base slug is appended to its parent's path:
   `raw_path = f"{parent.section_path}/{slugify(title)}"`
   Yielding `/hardware-subsystems/warnings-and-precautions` vs `/software-subsystems/warnings-and-precautions`.
2. Sibling collisions within the exact same parent section are tracked with a collision counter and disambiguated:
   `/specifications`, `/specifications-2`.
3. Every node is assigned a unique UUID in SQLite, while its canonical `section_path` serves as the deterministic anchor for version diffing.

---

## 4. Cryptographic Merkle Content Hashing

Requirement traceability demands tamper-proof verification that document text has not shifted. The system implements a **hierarchical Merkle hashing scheme**:

```
                       [ Document Root Hash ]
                       SHA256(Root1 | Root2)
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       [ Section 1 Hash ]              [ Section 2 Hash ]
       SHA256(Type + Title +           SHA256(Type + Title +
         Content + Child Hashes)         Content + Child Hashes)
                 │                               │
          ┌──────┴──────┐                 ┌──────┴──────┐
          ▼             ▼                 ▼             ▼
     [ Paragraph ]   [ Table ]       [ Paragraph ]  [ Sub-heading ]
```

1. **Leaf Nodes** (paragraphs, lists, tables, figures):
   $$\text{Hash} = \text{SHA-256}\Big(\text{json\_serialize}\big(\text{type}, \text{title}, \text{normalized\_content}, \text{meta}\big)\Big)$$
   Content is normalized (whitespace collapsed) so trivial formatting artifacts do not cause false modification alerts.
2. **Container Nodes** (sections, headings):
   $$\text{Hash} = \text{SHA-256}\Big(\text{json\_serialize}\big(\text{type}, \text{title}, \text{content}, \text{sorted}(\text{child\_hashes})\big)\Big)$$
3. **Document Root Hash**:
   $$\text{RootHash} = \text{SHA-256}\Big(\text{TopNode}_1\text{.hash} \parallel \text{TopNode}_2\text{.hash} \parallel \dots\Big)$$

**Benefit**: If a single requirement in subsection 2.1.2 changes, the hash of that subsection, its parent section, and the document root hash change predictably, while all unrelated sibling sections retain identical hashes.

---

## 5. Document Versioning & AST Diff Engine

When version `v2` is uploaded, both `v1` and `v2` are preserved independently in SQLite. The `VersionService` compares them using semantic section path alignment:

```
Version 1 Nodes                    Version 2 Nodes
  /1-overview          ═══=═══>      /1-overview         => UNCHANGED (hashes match)
  /2-radiation/2.1     ───────>      /2-radiation/2.1    => MODIFIED  (120 kV -> 140 kV)
  /2-radiation/2.2     ───────>      /2-radiation/2.2    => MODIFIED  (20 ms -> 15 ms)
  [None]               ───────>      /2-radiation/2.3    => ADDED     (Pediatric protocol)
  /3-hardware/warnings ───────>      [None]              => DELETED   (Hardware chapter removed)
```

For every modified node, the diff engine computes:
- `unified_diff`: Standard unified diff format showing line additions and removals.
- `changes_summary`: Human-readable summary (e.g. `"1 line(s) added, 1 line(s) removed"`).
- `similarity_ratio`: SequenceMatcher similarity score (0.0 to 1.0).

---

## 6. Version-Pinned Selections & Guarantee of Immutability

In QA engineering, users select specific requirements to test (e.g. selecting Section 2.1 voltage limit).

### The Invariant
> **"Old selections must retain their original text after new versions are uploaded."**

### Implementation
1. When a user creates a selection on `v1`, `SelectionService`:
   - Pins the foreign key strictly to `version_id = v1_id`.
   - Concatenates the extracted text of the selected nodes and saves it into `pinned_content_snapshot`.
   - Computes and persists the SHA-256 `content_hash` of this snapshot.
2. When `v2` is ingested later, `v1` records in SQLite are never modified.
3. When retrieving the selection, it returns the immutable snapshot and hash captured at selection time, ensuring that downstream verification records remain auditable under regulatory scrutiny.

---

## 7. AI Test-Case Generation with Gemini

The system uses the official Google Gen AI SDK (`google-genai`) with model `gemini-3.8-flash`.

### A. Prompt Engineering for Medical Software Standards
The prompt conditions the LLM as a Medical Device Software QA Engineer adhering to **IEC 62304**:
- Generates 3 to 5 test cases.
- Enforces fields: `test_case_id`, `title`, `description`, `type`, `preconditions`, `steps`, `expected_results`, `severity`, `traceability`.
- Demands verbatim requirement quotes in `traceability.requirement_quote` for direct compliance traceability.

### B. Strict Pydantic Schema Enforcement
- Utilizes `response_mime_type="application/json"` and `response_json_schema=GeminiTestCaseOutput.model_json_schema()`.
- Validates the resulting array length ($3 \le N \le 5$).
- Strips any accidental markdown code fences (` ```json `) defensively.
- Rejects empty action steps or missing expected results.

### C. Resilient Error Handling & Offline Mocking
- Handles quota errors, network timeouts, and malformed outputs by wrapping them in `LLMGenerationError` with HTTP 502 status codes.
- Supports a deterministic synthetic generator for test environments (`use_mock=True`) so the test suite runs offline without API tokens or network latency.

---

## 8. Real-Time Staleness Detection

Medical device regulations mandate that verification tests reflect active design inputs. When requirements change, tests generated against obsolete requirements become **stale**.

### Staleness Evaluation Flow
When a test case or generation batch is retrieved:
1. Identify the source nodes and `source_version_id` (e.g., `v1`).
2. Identify the active/latest document version (e.g., `v2`).
3. If `latest_version == source_version`:
   $\rightarrow$ `UP_TO_DATE`.
4. If `latest_version != source_version`:
   - Look up matching nodes in `v2` by `section_path`.
   - **Case A (Node Deleted)**: If any source node is absent in `v2` $\rightarrow$ `STALE_DELETED`.
   - **Case B (Node Modified)**: If node hashes differ $\rightarrow$ `STALE_MODIFIED`. The system generates a unified diff explaining what changed between the requirement version tested and the current document.
   - **Case C (Node Unchanged)**: If all source node hashes match their counterparts in `v2` $\rightarrow$ `UP_TO_DATE`.
5. Logs each staleness evaluation into MongoDB's `staleness_audits` collection for quality audit history.

---

## 9. Current Limitations & Future Work

| Area | Current Implementation | Planned Production Enhancement |
|---|---|---|
| **Complex Table Spanning** | Markdown grid extraction via `page.find_tables()` | Multi-line wrapped cell parsing using OCR layout models (e.g., LayoutLMv3) for nested headers |
| **Major Document Restructuring** | Aligns sections using semantic hierarchical paths (`section_path`) | Vector semantic embeddings (e.g. `gemini-embedding-2`) to track sections if chapters are completely reorganized |
| **Real-time Notifications** | Staleness evaluated on-demand during retrieval | Async event bus (Redis / Kafka) to broadcast webhook notifications to external test runners when requirements change |
| **Document Formats** | High-performance PDF parser with OCR | Extend modular parser interface to support DOCX and DITA XML formats |
