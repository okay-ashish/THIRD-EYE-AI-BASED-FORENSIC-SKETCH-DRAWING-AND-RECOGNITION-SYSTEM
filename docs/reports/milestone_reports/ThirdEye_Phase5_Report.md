# ThirdEye — Phase 5: Forensic Engine Integration and Case Artifact Persistence
**Executive Engineering & Forensic Integrity Verification Report**
**Date:** October 11, 2026 | **Environment:** Windows (Localhost) | **Isolation:** 100% In-Memory SQLite | **Database Engine:** MySQL 8.0 Protected (Fail-Closed)

---

## 1. Executive Summary

Phase 5 has successfully connected ThirdEye's core forensic capabilities (Composite Sketch Constructor, Sketch-to-Face Reconstruction, Face Variations, Biometric Face Recognition, and A4 Case Poster Draft Generation) directly into the sequential case investigation workflow established in Phase 4.

Every forensic operation now executes strictly within an authorized case context, ingesting verified source evidence and registering generated outputs as immutable, derived case artifacts beneath private case storage (`instance/case_storage/<complaint_number>/generated/`) using randomized filenames, SHA-256 cryptographic digests, explicit source-lineage links (`source_evidence_id`), and comprehensive audit timeline records in `ComplaintTimeline`.

All 14 Phase 5 verification gates have been verified with 100% pass rates across automated test suites, with zero live MySQL writes, zero schema modifications, and zero uncommitted Git push/commit actions.

---

## 2. Feature-Integration Matrix

| Forensic Feature / Tool | Case-Linked Route | Access Guard | Primary Source Artifact | Persisted Derived Artifact Type | Provenance & Disclaimers | Integration Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Composite Sketch Constructor** | `POST /cases/<id>/sketch` | Branch A only; case approved | Eyewitness input (Canvas / Layered components) | `sketch` (`source_kind='generated'`) | `generation_method='composite_layers'`; SHA-256 digest calculated | **Fully Integrated & Operational** |
| **Sketch-to-Face Reconstruction** | `POST /cases/<id>/reconstruct` | Branch A only; requires prior sketch artifact | Derived `sketch` artifact belonging to same case | `reconstructed_face` (`source_kind='generated'`) | `source_evidence_id` linked; Label: *"AI-generated reconstruction — illustrative only; not a verified identity"* | **Fully Integrated & Operational** |
| **Face Appearance Variations** | `POST /cases/<id>/variations` | Branch A, B, or C; requires authorized source | Branch A: `reconstructed_face` / `sketch`; Branch B: authentic photo; Branch C: authentic masked photo | `variation` (`source_kind='generated'`) | `source_evidence_id` linked; Branch C includes mandatory *"Computer-generated probable appearance"* notice | **Fully Integrated & Operational** |
| **Biometric Face Recognition** | `GET/POST /cases/<id>/recognition` | Branch B only; authentic photo required | Authentic uploaded `photo` (`source_kind='uploaded'`) | None (Investigative lead query against `Person` DB) | Rejects synthetic sketches, speculative faces, and occluded images; Advisory: *"Investigative lead only; not conclusive proof of guilt"* | **Fully Integrated & Operational** |
| **Case Poster Draft Generator** | `POST /cases/<id>/poster` | Branch A, B, or C; stage prerequisites met | Branch A: derived reconstruction/sketch; Branch B/C: authentic photo | `poster` (`source_kind='generated'`, `access_level='internal'`) | Default access level `internal`; `source_evidence_id` linked; Vector A4 PDF generation via ReportLab | **Fully Integrated & Operational** |
| **Poster Administrative Approval** | `POST /cases/<id>/poster/<ev_id>/approve` | Admin role required; validates case linkage | Internal draft `poster` artifact | Updates `access_level` to `public_notice` | Admin actor ID, timestamp, and audit event `poster_approved` recorded | **Fully Integrated & Operational** |
| **Public Notice Poster Download** | `GET /public/cases/<id>/posters/<ev_id>` | Publicly accessible ONLY if approved | Admin-approved poster artifact | Download stream of PDF notice | Denies unapproved drafts with `403 Forbidden`; serves approved notices with `200 OK` | **Fully Integrated & Operational** |
| **Private Evidence Stream** | `GET /cases/<id>/evidence/<ev_id>/view` | Case owner, Admin, or `public_notice` | Stored file in `case_storage/` | Streamed MIME response | Confined to `case_storage/`; traversal protection; 404 on cross-case mismatch | **Fully Integrated & Operational** |

---

## 3. Secure Case-Linked Artifact Storage & Provenance Rules

1. **Storage Confinement Outside `static/`:**
   - All generated forensic outputs are written to disk under `instance/case_storage/<complaint_number>/generated/`.
   - Files are never stored under public web-accessible directories (`static/uploads/`, `static/generated_faces/`, etc.).
2. **Cryptographic Randomization & Traversal Defense:**
   - Filenames are generated using unguessable, cryptographically secure tokens: `<evidence_type>_<token_hex(12)>.<ext>`.
   - File paths are strictly validated using `os.path.commonpath([case_dir, abs_dest]) == case_dir` to block directory traversal attacks.
3. **Database-Backing via Existing Schema:**
   - Reuses the existing `ComplaintEvidence` model without schema modifications or redundant tables.
   - Normalized `evidence_type` values (`sketch`, `reconstructed_face`, `variation`, `poster`, `photo`) adhere strictly to `ALLOWED_EVIDENCE_TYPES`.
   - Stores `source_kind='generated'`, `storage_path`, `original_filename`, `mime_type`, `file_size_bytes`, `sha256_hex`, and `generation_method`.
4. **Transaction Rollback & Disk Cleanup Guarantee:**
   - In `services/workflow_service.py` (`save_case_artifact`), if `db.session.commit()` fails or raises an error, `db.session.rollback()` is executed immediately, and the newly written file on disk is deleted using `os.unlink()`.
   - Zero orphaned or unreferenced files remain on disk after a failed transaction.
5. **Direct Source Provenance Linkage:**
   - Every derived artifact records `source_evidence_id`, establishing a tamper-proof lineage back to the primary evidence or preceding forensic stage.

---

## 4. Branch Execution & Workflow Behavior

### Branch A: No Photograph Available (Witness Description Only)
1. **Stage 1 (Composite Sketch):** Eyewitness composite constructed and persisted as `sketch` artifact with `generation_method='composite_layers'`.
2. **Stage 2 (Facial Reconstruction):** Unlocked only after a sketch artifact exists. Output persisted as `reconstructed_face` with explicit advisory label:
   > *"AI-generated reconstruction — illustrative only; not a verified identity."*
3. **Stage 3 (Appearance Variations):** Uses derived reconstruction as base image to simulate demographic, hairstyle, and facial hair variations.
4. **Stage 4 (Case Poster Draft):** Compiles case metadata, investigating officer contact, and derived reconstruction into an internal draft A4 PDF.
5. **Biometric Recognition:** Strictly **prohibited** on Branch A. Attempting to access recognition routes redirects with a policy warning explaining that biometric matching cannot be executed against synthetic sketches.

### Branch B: Authentic Unmasked Photograph Available
1. **Preservation of Authentic Evidence:** The original photograph remains untouched with `source_kind='uploaded'` and `evidence_type='photo'`. Its cryptographic SHA-256 hash is invariant.
2. **Bypass of Synthetic Steps:** Sketch construction and sketch-to-face reconstruction are automatically bypassed by default. Direct HTTP requests to `/sketch` or `/reconstruct` are redirected with stage policy notices.
3. **Controlled Biometric Recognition:** Offered as a dedicated, controlled operation strictly referencing the authentic uploaded photo. Matches are queried against enrolled `Person` records.
4. **Human Review & Uncertainty Disclaimer:** The recognition interface prominently displays a forensic uncertainty advisory:
   > *"Forensic Biometric Notice: Biometric candidate matches provide investigative intelligence only and do NOT constitute conclusive proof of identity or legal guilt. Mandatory human expert verification is required."*
5. **Poster Generation:** Formulates a suspect identification notice using the authentic photograph, preserved as an internal draft until Admin approval.

### Branch C: Masked or Occluded Photograph Available
1. **Authentic Evidence Preservation:** Genuine masked image is preserved in `case_storage/` without modification.
2. **Optional Probable Appearance:** Probable appearance feature is strictly optional and accompanied by the mandatory disclaimer:
   > *"Computer-generated probable appearance — illustrative only; not a recovered or verified identity."*
   The system never represents hidden facial features as recovered facts.
3. **Strict Biometric Prohibition:** Automated biometric recognition is **strictly locked and prohibited** on Branch C. The system rejects recognition requests on masked or occluded images server-side.
4. **Notice Distribution:** Case proceeds directly to an official poster draft using the genuine masked photograph.

---

## 5. Poster Draft & Administrative Approval Workflow

1. **Default Draft Status:** Newly generated posters are assigned `access_level='internal'`.
2. **Server-Side Admin Enforcement:**
   - Poster approval route (`POST /cases/<complaint_id>/poster/<evidence_id>/approve`) enforces `@login_required` and verifies `session.get('role') == 'admin'`. Unauthorized citizen requests receive `403 Forbidden`.
   - The route validates that the artifact belongs to the specified case and is of type `poster`.
3. **Public Notice Authorization Policy:**
   - Public download route (`GET /public/cases/<complaint_id>/posters/<evidence_id>`) strictly returns `403 Forbidden` if `access_level != 'public_notice'`.
   - Upon Admin approval, `access_level` transitions to `public_notice`, and the route serves the poster PDF with `200 OK`.
4. **Audit Trail Recording:**
   - Approval generates an audit timeline entry (`event_type='poster_approved'`) recording the approving Admin's user ID, timestamp, and case reference.
5. **No Silent Overwriting:**
   - Multiple poster generations generate separate, distinct artifacts with unique cryptographic IDs and filenames, preserving historical drafts.

---

## 6. Audit & Test Results

All test suites were executed sequentially using `scripts/run_isolated_tests.py` with 100% in-memory SQLite isolation (`sqlite:///:memory:`) and fail-closed MySQL interception.

### Summary of Test Execution:

| Test Suite | Gates Covered | Test Count | Pass Rate | Execution Time | Notes / Details |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `test_phase2_complaint_models.py` | Phase 2 Schema & RBAC | 11 / 11 | **100% PASS** | 2.359s | Table constraints, two roles, zero BLOB columns |
| `test_phase3_complaints.py` | Phase 3 Complaint Wizard | 29 / 29 | **100% PASS** | 26.712s | Draft wizard, evidence upload, submission immutability |
| `test_phase4_workflow.py` | Phase 4 Sequential Workflow | 16 / 16 | **100% PASS** | 14.281s | Role dashboards, officer assignment, stage guards |
| `test_phase5_forensic_artifacts.py` | Phase 5 Forensic & Storage | 14 / 14 | **100% PASS** | 12.549s | All 14 Phase 5 verification gates |
| `scratch/real_app_verifier.py` | Real App Route E2E | 7 / 7 | **100% PASS** | 4.810s | Real HTTP routes, session cookies, CSRF, storage |
| **Total Test Verification** | **All Phase 1–5 Gates** | **77 / 77** | **100% PASS** | **60.711s** | **Zero failures, zero regressions** |

### Breakdown of Phase 5 Test Gates (`test_phase5_forensic_artifacts.py`):
1. `test_01_branch_a_sketch_registration_and_provenance` — **PASSED**
2. `test_02_reconstruction_prerequisite_enforcement` — **PASSED**
3. `test_03_derived_artifacts_source_provenance_linkage` — **PASSED**
4. `test_04_branch_b_preserves_original_and_skips_sketch_conversion` — **PASSED**
5. `test_05_recognition_rejects_sketches_speculative_images_and_cross_case_artifacts` — **PASSED**
6. `test_06_branch_c_probable_appearance_optional_and_disclaimed` — **PASSED**
7. `test_07_cross_case_and_unauthorized_artifact_retrieval_blocked` — **PASSED**
8. `test_08_transaction_rollback_prevents_unreferenced_artifacts` — **PASSED**
9. `test_09_poster_drafts_remain_private_until_explicit_admin_approval` — **PASSED**
10. `test_10_public_notice_access_enforcement` — **PASSED**
11. `test_11_repeated_requests_do_not_silently_overwrite_prior_artifacts` — **PASSED**
12. `test_12_audit_timeline_entries_correspond_to_successful_operations` — **PASSED**
13. `test_13_submitted_original_evidence_immutability` — **PASSED**
14. `test_14_zero_live_mysql_connection` — **PASSED**

### Model Execution vs. Mocking Strategy:
- **Real Execution:** Input validation, session management, file serialization, SHA-256 computation, disk I/O, database transactions, ReportLab A4 vector PDF generation, OpenCV decoding, and HTTP response handling ran with **100% real code**.
- **Mocked Inference:** Only heavy neural network inference calls (`reconstruct_face` CycleGAN synthesis and `generate_face_variations` landmark morphing) were mocked in automated unit tests to respect the 8 GB RAM / integrated GPU hardware constraints. The route wrappers, storage persistence, and artifact linking logic were fully tested with real files.

---

## 7. Captured Visual Evidence & Workspace Screenshots

High-resolution screenshots were captured using headless Google Chrome (`1366x1024`) backed by the isolated test server and saved to `ThirdEye_Phase5_Screenshots`:

1. `01_case_workspace_branch_a_artifacts.png` (295 KB):
   - Demonstrates Branch A composite sketch, facial reconstruction, appearance variation, and internal draft poster artifacts registered in the Case Evidence repository with full disclaimers.
2. `02_case_workspace_branch_b_photo.png` (275 KB):
   - Demonstrates Branch B workflow with authentic uploaded photograph preserved, sketch/reconstruction stages bypassed, and poster draft generated.
3. `03_case_workspace_branch_c_masked.png` (273 KB):
   - Demonstrates Branch C masked photograph case with optional probable appearance variation and strict biometric recognition lockout.
4. `04_admin_dossier_poster_approval.png` (387 KB):
   - Demonstrates Admin Case Review dossier with corrected GPS Coordinates label, attached evidence files list, and poster approval action resulting in `Approved Notice` badge.
5. `05_branch_b_biometric_recognition.png` (337 KB):
   - Demonstrates controlled biometric recognition screen with prominent Forensic Uncertainty & Mandatory Human Review advisory banner.

---

## 8. Defect Resolution & Polish

1. **GPS Coordinates Label Inconsistency Resolved:**
   - In `templates/admin_case_review.html`, corrected the label to prevent `(None)` display when location source is unset: `GPS Coordinates{% if complaint.location_source and complaint.location_source != 'None' %} ({{ complaint.location_source|replace('_', ' ')|capitalize }}){% endif %}`.
2. **Schema Type Normalization:**
   - Standardized artifact registration to use `evidence_type='variation'` (matching `ALLOWED_EVIDENCE_TYPES`) rather than `face_variation`.
3. **Database Transaction Rollback Disk Safety:**
   - Added automatic file unlinking in `save_case_artifact` if database commit raises an exception, preventing unreferenced files.
4. **Non-Admin Poster Approval Rejection:**
   - Added explicit `abort(403)` check in `approve_case_poster` for non-admin accounts.

---

## 9. Integrity and Boundary Confirmations

- **Git Status:** Clean of unauthorized commits or pushes. All modifications remain staged/unstaged in the working tree.
- **Database Safety:** Zero live MySQL migrations or writes occurred. The live database remains identical to pre-Phase 5 state.
- **Next Phase:** Phase 6 has **not** been started. Execution has halted cleanly awaiting review.
