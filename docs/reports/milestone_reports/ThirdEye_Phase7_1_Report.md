# ThirdEye — Phase 7.1: Final Status, Masked-Photo and Model-License Verification Report

**Date:** 2026-10-11  
**Project Root:** `C:\ThirdEye`  
**Target Environment:** Windows 11 (64-bit), Anaconda Python 3.11 (`C:\Users\LENOVO\anaconda3\envs\ThirdEye311\python.exe`), ~8 GB RAM, Intel Integrated Graphics (CPU Inference Only)  
**Deliverable Path:** `C:\Users\LENOVO\Desktop\ThirdEye_Phase7_1_Report.md`  

---

## Executive Summary

Phase 7.1 conducted an exhaustive investigation into three specific areas of the ThirdEye platform:
1. **Canonical Status Model & Addendum Lifecycle:** Confirmed that `under_investigation` does not exist in any executable code, database models, table constraints, or transition maps. Submitting a citizen addendum canonically and reliably returns the case to `under_review`. Two narrative/documentation inconsistencies in `README.md` and the Phase 7 report were identified and corrected.
2. **Branch C Masked-Photo Probable-Appearance Implementation:** Verified that the masked-photo probable-appearance feature is a **heuristic, geometry-anchored appearance synthesis pipeline** using the BiSeNet semantic face parser (`model/face_parsing/efficientnet_b0.onnx`) and Delaunay mesh warping, rather than a specialized neural mask-removal/inpainting GAN. Real CPU execution was verified with synthetic masked data, confirming byte-for-byte preservation of original evidence, mandatory project disclaimers, strict biometric blocking, and authentic poster generation fallback.
3. **Model License & Redistribution Audit:** Conducted a rigorous separation of research architecture licenses from pretrained checkpoint licenses. Concluded that `cyclegan_model.pt` (checkpoint training provenance UNVERIFIED) and `efficientnet_b0.onnx` (checkpoint training provenance UNVERIFIED; upstream code mentions CelebAMask-HQ non-commercial workflow) should be excluded from public release pending provenance verification as a precautionary measure.
4. **Complete Isolated Regression Verification:** Executed all 12 regression test suites sequentially under in-memory SQLite isolation. All 144 verification checks passed (135 unittest test cases + 9 real application route integration checks) in 414.96 seconds with zero failures and zero errors.

---

## 1. Canonical Complaint Status Findings & Corrections

### A. Code & Schema Audit
An exhaustive inspection was performed across:
- `models.py` ([Complaint](file:///c:/ThirdEye/models.py#L90), [ALLOWED_COMPLAINT_STATUSES](file:///c:/ThirdEye/models.py#L13))
- `services/workflow_service.py` ([ADMIN_PERMITTED_TRANSITIONS](file:///c:/ThirdEye/services/workflow_service.py#L40), [USER_PERMITTED_TRANSITIONS](file:///c:/ThirdEye/services/workflow_service.py#L53), [submit_case_addendum](file:///c:/ThirdEye/services/workflow_service.py#L230))
- `app.py` ([respond_information_request](file:///c:/ThirdEye/app.py#L1884))
- HTML templates and automated test suites.

#### Key Findings:
1. **Canonical Status List:**
   The exact, executable canonical status list defined in `models.py` comprises 10 states:
   - `draft`
   - `submitted`
   - `under_review`
   - `information_requested`
   - `rejected`
   - `approved`
   - `assigned`
   - `investigation_in_progress`
   - `awaiting_further_evidence`
   - `closed`
2. **Absence of `under_investigation`:**
   `under_investigation` is **not present** anywhere in executable application code, SQLAlchemy model constraints (`check_valid_complaint_status`), or transition dictionaries. Attempting to assign `complaint.status = 'under_investigation'` raises an immediate validation failure via `@validates('status')`:
   `ValueError: Invalid complaint status: 'under_investigation'.`
3. **Persisted Addendum Behavior in Executable Code:**
   In [services/workflow_service.py](file:///c:/ThirdEye/services/workflow_service.py#L274-L277):
   ```python
   # 2. Transition back to 'under_review'
   old_status = complaint.status
   complaint.status = 'under_review'
   complaint.updated_at = datetime.utcnow()
   ```
   When a citizen responds to an administrative request for more information via `submit_case_addendum()`, the application strictly sets the status to **`under_review`** so that the administrator can re-evaluate the case with the newly provided addendum.

### B. Identified Documentation Inconsistencies & Corrections
The appearance of `under_investigation` was traced to documentation-only errors:
1. **`ThirdEye_Phase7_Report.md` Table Typo (Line 98):**
   - *Previous Text:* `HTTP 302; Transitions to information_requested and returns to under_investigation upon addendum.`
   - *Correction:* Corrected to `under_review` on Desktop and scratch report files.
2. **`README.md` ASCII Flowchart (Lines 44–48):**
   - *Previous Flow:* The diagram erroneously drew the arrow from `(Citizen submits addendum)` pointing into `[Assigned] / [Investigation in Progress]`.
   - *Correction:* Updated the diagram so the addendum submission loops back to `[Under Review]`:
   ```
   [Draft]
      │ (Citizen completes wizard)
      ▼
   [Submitted]
      │ (Admin initial triage)
      ▼
   [Under Review] ◄─────────────────────────────────────────────┐
      │ │                                                       │
      │ └─── (Admin requests details) ───► [Information Requested]
      │                                       │ (Citizen submits addendum)
      │ (Admin approves case)                 └─────────────────┘
      ▼
   [Approved] ──► [Assigned] ──► [Investigation in Progress]
      │
      ├─► Branch A, B, or C Forensic Workspace
      ├─► Case-Bound Biometric Recognition (POST route only)
      ├─► Investigative Poster Draft Generation
      ├─► Admin Poster Review & Official Approval
      ▼
   [Closed]
   ```

### C. Persisted Addendum Lifecycle Verification (Isolated SQLite)
A focused automated test (`test_01_canonical_status_model_and_addendum_lifecycle` in `scratch/test_phase7_1_verification.py`) verified the complete lifecycle:
1. Citizen creates draft and submits complaint &rarr; Status is `submitted`.
2. Admin begins review &rarr; Status transitions to `under_review`.
3. Admin requests information &rarr; Status transitions to `information_requested`. Case timeline appends event `information_requested` with Admin actor ID and request message.
4. Citizen responds via `submit_case_addendum()` with text notes and a supplementary PNG file.
5. Case transitions back to `under_review` (verified via `fresh_persisted.status == 'under_review'`).
6. Original narrative text and original evidence file remain 100% byte-for-byte and textually intact (`sha256_hex` matches pre-submission hash).
7. Supplementary evidence is appended as a new record with `source_kind='uploaded'`.
8. Timeline records event `information_response` with Citizen actor ID, previous status `information_requested`, and new status `under_review`.

---

## 2. Actual Branch C Probable-Appearance Implementation

### A. Architecture and Algorithm Classification
A comprehensive code audit traced the execution path for Branch C masked photographs:

| Dimension | Actual Implementation Details |
|---|---|
| **Entry Route** | `POST /cases/<int:complaint_id>/variations` in [app.py](file:///c:/ThirdEye/app.py#L710-L799) |
| **Permission Guard** | `can_access_tool(complaint, 'probable_appearance')` in [services/workflow_service.py](file:///c:/ThirdEye/services/workflow_service.py#L317-L375) |
| **Service Engine** | `generate_face_variations()` in [face_variations.py](file:///c:/ThirdEye/face_variations.py#L1265) |
| **Model / Pipeline** | Multi-tier landmark extraction (`detect_landmarks_robust`) + BiSeNet EfficientNet-B0 semantic parser (`model/face_parsing/efficientnet_b0.onnx`) + Piecewise Affine / Delaunay mesh warping + procedural alpha blending |
| **Classification** | **Heuristic, geometry-anchored appearance synthesis pipeline**. It is **NOT** a specialized neural mask-removal or blind inpainting GAN. |

### B. Execution Mechanism on Masked Photographs
1. **Landmark Detection:** On a masked photo, dlib and the robust fallback detect unoccluded cranial landmarks (eyes, eyebrows, forehead hairline, temple crests). Lower-face landmarks (mouth, lips, chin) are estimated based on anthropometric cranial proportions or facial symmetry.
2. **Semantic Segmentation:** The BiSeNet parser segments visible facial skin, hair, and background.
3. **Appearance Variation Overlays:** The system synthesizes alternative hairstyles (e.g., Short Wave, Curly, Bald), headwear (caps, turbans), or longitudinal age progression across the visible upper cranial vault.
4. **Lower Face Handling:** The physical mask covering the lower face remains in place or is blended with procedural skin tones. The system **does not** reconstruct real hidden lips, teeth, or mandibular structure.

### C. Forensic Safety Safeguards Verified
Real execution was verified using synthetic masked test data in `test_02_branch_c_probable_appearance_algorithm_and_safety`:
1. **Original Evidence Immutability:** The authentic masked photograph remains byte-for-byte unchanged; its SHA-256 digest is preserved.
2. **Optional Operation:** Probable appearance generation is strictly elective and initiated only upon investigator request.
3. **Derived Storage & Provenance:** The output is saved separately under `instance/case_storage/<complaint_number>/generated/` with `evidence_type='variation'` linked to `source_evidence_id`.
4. **Mandatory Project Disclaimer:**
   Recorded in database metadata (`generation_method`) and flashed in the user interface:
   *“Computer-generated probable appearance — illustrative only; not a recovered or verified identity.”*
5. **Biometric Recognition Block:**
   Biometric matching is strictly prohibited on masked and speculative images:
   - `can_access_tool(case_c, 'recognition')` returns `False` (*"Biometric matching is strictly prohibited for masked or occluded suspect photographs"*).
   - `get_eligible_recognition_evidence(case_c)` returns an empty list.
   - Calling `validate_recognition_source_evidence()` raises a `ValueError`.
6. **Poster Fallback:** High-resolution DIN A4 poster generation proceeds using the **authentic masked photograph**, ensuring public alerts depict ground-truth evidence.

### D. Remaining Limitation
The system cannot magically "see through" physical cloth or paper masks. Generated variations should only be used to explore hairstyle or cranial variations, not to guess an individual's actual mouth or chin geometry.

---

## 3. Pretrained Model License & Redistribution Audit

A rigorous legal and provenance review was conducted for all model assets in the repository:

### Model-by-Model Analysis

| Model File | File Path | File Size | Research Architecture License | Checkpoint / Pretrained Weights License & Origin | Redistribution Recommendation |
|---|---|---|---|---|---|
| **CycleGAN Generator** | `model/sketch_to_face/cyclegan_model.pt` | 30.04 MB (31,495,009 B) | **BSD 2-Clause License** (Zhu et al., Berkeley AI Research) | **UNVERIFIED.** Pretrained TorchScript checkpoint. Training dataset is not explicitly documented or linked in metadata. | **EXCLUDE PENDING VERIFICATION (PRECAUTIONARY).** Keep excluded from public Git releases until origin and redistribution permissions are verified. |
| **BiSeNet Face Parser** | `model/face_parsing/efficientnet_b0.onnx` | 26.28 MB (27,560,383 B) | **MIT License** (GitHub: `Mrkomiljon/face-parsing`) | **UNVERIFIED.** Upstream repository documents a workflow using CelebAMask-HQ dataset (non-commercial research terms), but ThirdEye's specific ONNX checkpoint cannot be conclusively linked to that exact training run. | **EXCLUDE PENDING VERIFICATION (PRECAUTIONARY).** Do not redistribute in public repository pending verification of exact checkpoint provenance and redistribution rights. |
| **FRAN Re-Aging Network** | `model/face_reaging/face_reaging.onnx` | 118.48 MB (124,233,728 B) | **Disney Research Non-Commercial License** (Naruniec et al., 2022) | **NON-COMMERCIAL / STRICT RESEARCH USE ONLY.** Checkpoint exported via `Glat0s/face_reaging-onnx`. Exceeds GitHub 100 MB hard limit. | **STRICTLY EXCLUDED.** Already protected by `.gitignore`. ThirdEye's built-in procedural fallback activates automatically. |
| **Mask Blending Assets** | `model/face_reaging/mask1024.jpg`, `mask512.jpg` | 186 KB & 7.6 KB | N/A | Procedural elliptical grayscale masks created for continuous edge feathering. | **ELIGIBLE FOR RELEASE.** |
| **Landmarks & Embeddings** | Managed via package `face-recognition-models` | ~100 MB | Boost Software License 1.0 / MIT License | Managed as standard external pip dependencies (Davis King / Adam Geitgey). | **SAFE TO DISTRIBUTE AS DEPENDENCY.** (Not committed to repository source). |

> **Precautionary Model Exclusion Notice:** Recommendations to exclude model checkpoint files from public distribution are conservative risk-mitigation precautions pending explicit provenance and redistribution permission verification, not definitive legal rulings.

### Summary Recommendation for Public Release
To avoid copyright encumbrances:
1. Do not track large or non-commercially restricted weight checkpoints (`cyclegan_model.pt`, `efficientnet_b0.onnx`, `face_reaging.onnx`) directly in a public GitHub repository.
2. For academic project evaluation and local examination, local files function immediately without external network downloads.

---

## 4. Complete Automated Regression Test Results

All 12 regression test suites were executed sequentially using the isolated in-memory SQLite runner with fail-closed MySQL interception:

```bash
C:\Users\LENOVO\anaconda3\envs\ThirdEye311\python.exe scratch/run_all_phase7_regressions.py
```

### Complete Execution Summary Table

| # | Test Suite | Focus Area | Checks / Tests | Status | Duration |
|---|---|---|---|---|---|
| 1 | [test_phase2_complaint_models.py](file:///c:/ThirdEye/test_phase2_complaint_models.py) | Complaint schema, relationships, two-role model | 11 | **PASS** | 12.54s |
| 2 | [test_phase3_complaints.py](file:///c:/ThirdEye/test_phase3_complaints.py) | Citizen wizard, drafts, validation, submission | 29 | **PASS** | 69.59s |
| 3 | [test_phase4_workflow.py](file:///c:/ThirdEye/test_phase4_workflow.py) | Status transitions, assignments, timeline audit | 16 | **PASS** | 37.68s |
| 4 | [test_phase5_forensic_artifacts.py](file:///c:/ThirdEye/test_phase5_forensic_artifacts.py) | Artifact persistence, SHA-256 digests, private storage | 14 | **PASS** | 38.21s |
| 5 | [test_phase5_1_biometric_case_binding.py](file:///c:/ThirdEye/test_phase5_1_biometric_case_binding.py) | Case-bound biometrics, POST enforcement, negative detection | 15 | **PASS** | 37.27s |
| 6 | [test_phase6_security_reliability.py](file:///c:/ThirdEye/test_phase6_security_reliability.py) | URL guards, poster draft gating, role boundaries | 10 | **PASS** | 25.34s |
| 7 | [test_phase6_1_csrf_security.py](file:///c:/ThirdEye/test_phase6_1_csrf_security.py) | Flask-WTF CSRF validation on all state-changing routes | 14 | **PASS** | 45.00s |
| 8 | [test_phase6_2_config_security.py](file:///c:/ThirdEye/test_phase6_2_config_security.py) | Secret-key fail-closed, temporary dev key, config checks | 10 | **PASS** | 71.76s |
| 9 | [real_app_verifier.py](file:///c:/ThirdEye/scratch/real_app_verifier.py) | Real application routes & CSRF integration checks | 9 | **PASS** | 14.20s |
| 10 | [test_phase6_3_compatibility.py](file:///c:/ThirdEye/scratch/test_phase6_3_compatibility.py) | OpenCV 4.11, NumPy 1.26.4, dlib, and biometrics | 8 | **PASS** | 9.13s |
| 11 | [test_phase7_release_verifier.py](file:///c:/ThirdEye/scratch/test_phase7_release_verifier.py) | Real CycleGAN inference, Branch A/B/C release gates | 5 | **PASS** | 41.65s |
| 12 | [test_phase7_1_verification.py](file:///c:/ThirdEye/scratch/test_phase7_1_verification.py) | Canonical addendum lifecycle, Branch C implementation, model integrity | 3 | **PASS** | 12.60s |
| **TOTAL** | **12 Suites Sequentially Executed** | **Complete System Regression Verification** | **144** | **PASS (0 errors, 0 failures)** | **414.96s** |

---

## 5. Remaining Release Blockers and Prerequisites

1. **Model Checkpoint Redistribution (Policy Action):**
   - For a public open-source repository release, `cyclegan_model.pt` and `efficientnet_b0.onnx` should not be committed to Git history due to unverified training dataset clauses.
   - *Resolution:* Exclude checkpoints via `.gitignore` and provide an external setup script or download instructions in `README.md`.
2. **Database Initialization Prerequisite (Operational Step):**
   - A fresh clone requires initializing tables via `thirdeye_db.example.sql` or Flask shell (`db.create_all()`) and provisioning an administrator account (`python create_admin.py`).
   - The application does not automatically create tables at startup without explicit configuration.
3. **External Dependencies (Network & Browser Features):**
   - Incident mapping uses OpenStreetMap tiles via Leaflet; air-gapped environments cannot load map graphics (manual address text input remains functional).
   - Voice transcription requires a browser supporting the Web Speech API (Chrome / Edge); text entry remains functional across all browsers.

---

## 6. Git Status and Database Safety Confirmations

1. **Version Control Safety Confirmed:**
   - `git diff --check` executed with **exit code 0** (zero whitespace issues or line ending errors).
   - **Zero Git commits (`git commit`)** were executed.
   - **Zero Git pushes (`git push`)** were executed.
   - **Zero destructive Git cleanups (`git clean`, `git reset`, destructive `git restore`)** were executed.
   - All uncommitted changes across Phases 2 through 7.1 remain preserved in the working tree.
2. **Live Database Safety Confirmed:**
   - **Zero alterations or queries** touched the live MySQL database (`thirdeye_db`).
   - All tests used in-memory SQLite (`sqlite:///:memory:`) with library-level fail-closed MySQL interception.

---

## Conclusion & Stop Condition

ThirdEye Phase 7.1 is complete. The canonical status model has been verified, documentation is aligned, the Branch C heuristic implementation is honestly documented with its forensic limitations, model redistribution licenses are thoroughly analyzed, and all 144 verification checks pass with 100% success. Execution has halted as requested for final review.
