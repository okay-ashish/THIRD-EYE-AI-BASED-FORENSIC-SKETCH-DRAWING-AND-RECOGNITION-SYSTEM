# ThirdEye — Phase 7.4.1 Verification Report: Staging Test Isolation, Module Path Resolution, and Fallback Audit

**Date:** October 11, 2026  
**Environment:** Python 3.11.9 (Anaconda `ThirdEye311`) on Windows 11  
**Source Directory:** `C:\ThirdEye`  
**Staging Directory:** `C:\ThirdEye_Public_Release_Staging`  
**Database Dialect:** SQLite `:memory:` (Live MySQL `thirdeye_db` strictly blocked)  

---

## Executive Summary

Phase 7.4.1 conducted an in-depth isolation and module resolution audit of `C:\ThirdEye_Public_Release_Staging`, specifically evaluating `test_phase6_1_csrf_security.py`, `test_phase6_2_config_security.py`, and `scripts/run_isolated_tests.py`. 

### Key Findings & Verdict:
1. **Critical Isolation Finding (Release Blocker):** Both `test_phase6_1_csrf_security.py` (line 44) and `test_phase6_2_config_security.py` (line 50) contain a hardcoded `PROJECT_ROOT = r"C:\ThirdEye"`, inserting `C:\ThirdEye` at index 0 of `sys.path`. When executed outside the test runner or when test ordering varies, application modules (`app.py`, `models.py`) resolve to the **original project directory** rather than the staging folder. In `test_phase6_2`, subprocess calls explicitly execute with `cwd=PROJECT_ROOT` (`C:\ThirdEye`).
2. **Read vs. Write Verification:**
   - **Reads from `C:\ThirdEye`:** **YES**. Module imports and subprocesses read from `C:\ThirdEye`.
   - **Writes to `C:\ThirdEye`:** **NO**. Zero disk writes and zero database writes occur in `C:\ThirdEye`. Tests use in-memory SQLite (`sqlite:///:memory:`) and temporary OS directories (`tempfile.mkdtemp()`) which are cleanly destroyed in teardown.
3. **Source Modification Policy:** In strict adherence to Phase 7.4.1 instructions (*"If a problem requires source-code changes, report it and stop"*), no source files were modified. This path leakage is formally reported as an open portability defect requiring resolution before public redistribution.
4. **Checkpoint-Free Fallbacks Verified:** Tested and confirmed that procedural reconstruction fallbacks in `face_reconstruction.py` and landmark spline / procedural aging fallbacks in `face_variations.py` execute successfully with `engine_used = 'procedural_fallback'` in the absence of weights (`.pt`, `.onnx`).
5. **Checksum & Manifest Reconciliation:** All 319 staged files match their SHA-256 digests with zero discrepancies. Size units have been reconciled: exact size is **37,629,158 bytes**, which is **35.89 MiB** (binary mebibytes, IEC) or **37.63 MB** (decimal megabytes, SI).
6. **Isolated Test Execution:** Ran **55 fresh tests** plus the isolation self-check with live MySQL blocked. All passed with 100% success rate (0 errors, 0 failures).

---

## 1. Inspection of Test Files & Staging Runner

### 1.1 `test_phase6_1_csrf_security.py`
- **Location:** `C:\ThirdEye_Public_Release_Staging\test_phase6_1_csrf_security.py`
- **Path Logic (Lines 44–46):**
  ```python
  PROJECT_ROOT = r"C:\ThirdEye"
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  ```
- **Analysis:** Hardcodes the source repository path. Inserting `C:\ThirdEye` into `sys.path[0]` overrides the staging directory.
- **Storage & State:** Creates test storage via `tempfile.mkdtemp(prefix="thirdeye_phase6_1_test_storage_")` in the OS temp directory (`C:\Users\LENOVO\AppData\Local\Temp`), destroyed during `tearDownClass()`. Configures `sqlite:///:memory:`. Does not write to `C:\ThirdEye`.

### 1.2 `test_phase6_2_config_security.py`
- **Location:** `C:\ThirdEye_Public_Release_Staging\test_phase6_2_config_security.py`
- **Path Logic (Lines 50–52):**
  ```python
  PROJECT_ROOT = r"C:\ThirdEye"
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  ```
- **Subprocess Calls (Lines 164, 193, 222, 251, 258, 329):**
  ```python
  proc = subprocess.run([PYTHON_EXE, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True)
  ```
- **Analysis:** Subprocesses are launched with `cwd=PROJECT_ROOT` pointing to `C:\ThirdEye`. These processes read `app.py` and `.env` from `C:\ThirdEye`.
- **Database & State:** Subprocesses run lightweight startup and configuration tests with mocked/memory DB settings. Does not write to `C:\ThirdEye`.

### 1.3 `scripts/run_isolated_tests.py`
- **Location:** `C:\ThirdEye_Public_Release_Staging\scripts\run_isolated_tests.py`
- **Path Logic (Lines 37–39):**
  ```python
  PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  if PROJECT_ROOT not in sys.path:
      sys.path.insert(0, PROJECT_ROOT)
  ```
- **Analysis:** Correctly computes `PROJECT_ROOT` relative to `__file__`, resolving dynamically to `C:\ThirdEye_Public_Release_Staging`.
- **Pre-import Mechanism:** `verify_isolated_app()` imports `app` and `models` before test suites load, pinning them in `sys.modules`. However, when test suites are run standalone or when child processes are spawned, the hardcoded `C:\ThirdEye` paths in `test_phase6_1` and `test_phase6_2` take precedence.
- **Security Defenses:**
  - Enforces `SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"`
  - Blocks MySQL connections at library level via `mysql.connector.connect` monkeypatch
  - Asserts `db.engine.dialect.name == "sqlite"` (fails closed with code 101 on violation)

---

## 2. Actual Resolved Paths During Test Execution

Diagnostic tracing recorded the exact paths resolved during execution:

| Component / Symbol | Resolved File / Directory Path | Source Origin | Notes |
| :--- | :--- | :--- | :--- |
| **Current Working Directory (`os.getcwd()`)** | `C:\ThirdEye_Public_Release_Staging` | Staging Root | Test runner working directory |
| **Runner `PROJECT_ROOT`** | `C:\ThirdEye_Public_Release_Staging` | Dynamic (`__file__`) | Staging runner resolves properly |
| **Runner Module (`run_isolated_tests`)** | `C:\ThirdEye_Public_Release_Staging\scripts\run_isolated_tests.py` | Staging Folder | Loaded by Python |
| **`app.py` (pre-imported by runner)** | `C:\ThirdEye_Public_Release_Staging\app.py` | Staging Folder | If runner loads app before test suites |
| **`models.py` (pre-imported by runner)** | `C:\ThirdEye_Public_Release_Staging\models.py` | Staging Folder | If runner loads models before test suites |
| **`test_phase6_1_csrf_security.py`** | `C:\ThirdEye_Public_Release_Staging\test_phase6_1_csrf_security.py` | Staging Folder | Loaded from staging |
| **`t61.PROJECT_ROOT` Constant** | `C:\ThirdEye` | **Hardcoded Source** | Defined in test file line 44 |
| **`sys.path[0]` after `t61` import** | `C:\ThirdEye` | **Injected Path** | Mutated `sys.path` |
| **`app.py` (if imported after `t61`)** | `C:\ThirdEye\app.py` | **Original Project** | Path leakage via `sys.path[0]` |
| **`models.py` (if imported after `t61`)** | `C:\ThirdEye\models.py` | **Original Project** | Path leakage via `sys.path[0]` |
| **`test_phase6_2_config_security.py`** | `C:\ThirdEye\test_phase6_2_config_security.py` | **Original Project** | Resolved from `C:\ThirdEye` if `t61` loaded first! |
| **`t62` Subprocess `cwd`** | `C:\ThirdEye` | **Original Project** | Five subprocess test cases execute in `C:\ThirdEye` |

---

## 3. Read vs. Write Verification on Original `C:\ThirdEye`

Rigorous code audit and behavioral execution confirmed:

### Read Operations on `C:\ThirdEye`:
- **Status:** **DETECTED (CONFIRMED)**
- **Mechanisms:**
  1. `test_phase6_1_csrf_security.py` inserts `C:\ThirdEye` into `sys.path[0]`, causing Python module loader to read `app.py`, `models.py`, and `services/` from `C:\ThirdEye`.
  2. `test_phase6_2_config_security.py` inserts `C:\ThirdEye` into `sys.path[0]`.
  3. `test_phase6_2_config_security.py` runs `subprocess.run(..., cwd=PROJECT_ROOT)` with `cwd=r"C:\ThirdEye"`, causing child processes to inspect files and environment in `C:\ThirdEye`.
- **Impact:** The staging folder cannot function as a truly isolated, relocatable release artifact on an external system until these hardcoded paths are replaced with relative resolution (`os.path.dirname(os.path.abspath(__file__))`).

### Write Operations on `C:\ThirdEye`:
- **Status:** **ZERO (CLEAN)**
- **Verification:**
  1. Database writes: Both test suites enforce `sqlite:///:memory:`. Zero database rows or files are written to `C:\ThirdEye`.
  2. File uploads / storage: `test_phase6_1` configures `tempfile.mkdtemp()` in the system temporary directory and removes it during `tearDownClass`.
  3. Git status audit: `git status` in `C:\ThirdEye` confirms exactly 19 modified files and 16 untracked items—identical to the pre-staging state. Zero files added, modified, or deleted.

---

## 4. Checkpoint-Free Fallback Behavior Verification

The staging folder intentionally excludes binary model checkpoint files (`.pt`, `.onnx`, `.h5`). Inference modules were tested to ensure fallback behavior operates without error:

### 4.1 Sketch-to-Face Reconstruction Fallback (`face_reconstruction.py`)
- **Primary Model:** `model/sketch_to_face/cyclegan_model.pt` (Not staged / omitted).
- **Execution Test:** Invoked `reconstruct_face(png_bytes)` in staging environment.
- **Observed Behavior:**
  - `get_sketch_to_face_model` detects missing model file and logs:  
    `Model file not found at C:\ThirdEye_Public_Release_Staging\model\sketch_to_face\cyclegan_model.pt`
  - Engine automatically activates `reconstruct_face_procedural()`.
  - Output dictionary:
    - `"success"`: `True`
    - `"method"`: `"Computational Fallback Engine (Procedural)"`
    - `"ai_model_status"`: `"AI reconstruction model unavailable (Model file not found at C:\ThirdEye_Public_Release_Staging\model\sketch_to_face\cyclegan_model.pt). Using computational fallback."`
    - `"engine_used"`: `"procedural_fallback"`

### 4.2 Face Parsing & Appearance Variation Fallback (`face_variations.py`)
- **Primary Parsing Model:** `model/face_parsing/efficientnet_b0.onnx` (Not staged / omitted).
- **Primary Re-Aging Model:** `model/face_reaging/face_reaging.onnx` (Not staged / omitted).
- **Execution Test:** Queried ONNX runtime sessions:
  - `get_face_parser_session()` -> Returned `None` (Model file absent; skips ONNX initialization).
  - `get_fran_session()` -> Returned `None` (Model file absent; skips ONNX initialization).
- **Observed Behavior:**
  - Semantic segmentation gracefully falls back to anatomical landmark geometry spline mapping (`build_anatomical_region_map` fallback path).
  - Age progression gracefully falls back to anatomical procedural age engine (`_apply_procedural_age_adjustment`).

---

## 5. Staged-File Checksums & Manifest Reconciliation

### 5.1 Checksum Integrity Audit
- **Files Staged:** 319 files
- **Manifest Source:** `C:\ThirdEye\scratch\staging_manifest.json` & `C:\ThirdEye_Public_Release_Staging\STAGING_MANIFEST.md`
- **Audit Result:**
  - Missing files in staging: **0**
  - Checksum mismatches in staging: **0** (All 319 files match manifest SHA-256 digests)
  - Discrepancies against original `C:\ThirdEye` source files: **0** (100% byte-for-byte fidelity)

### 5.2 Size Unit Reconciliation
The Phase 7.4 report noted the staged footprint as `37,629,158 bytes (~35.89 MB)`. This mixed binary and decimal nomenclature:
- **Exact Byte Count:** `37,629,158 bytes`
- **Binary Mebibytes (IEC / base-2):** `37,629,158 / (1024 * 1024) = 35.88599... MiB` -> **35.89 MiB**
- **Decimal Megabytes (SI / base-10):** `37,629,158 / (1,000,000) = 37.62915... MB` -> **37.63 MB**
- **Correction:** The staged payload is **35.89 MiB** or **37.63 MB**.

---

## 6. Staging Test Runner Execution (Safe Test Suites)

To avoid duplicating the Phase 7.4 tests (`test_phase2`, `test_phase6_2`, `test_phase5_1`), Phase 7.4.1 executed previously unrun test suites through `scripts/run_isolated_tests.py` with live MySQL blocked:

| Test Suite File | Focus / Coverage | Tests | Duration | Result | Dialect Verified |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`scripts/run_isolated_tests.py --self-check`** | SQLite backend isolation & synthetic CRUD | 5 gates | 0.81s | **PASSED** | SQLite in-memory |
| **`test_phase4_workflow.py`** | 2-role RBAC, 10-status workflow lifecycle, Branch A/B/C pipelines, poster approvals | 16 | 15.13s | **PASSED** | SQLite in-memory |
| **`test_phase6_security_reliability.py`** | Session cookies, GET side-effects, evidence immutability, transaction rollback | 10 | 9.38s | **PASSED** | SQLite in-memory |
| **`test_phase3_complaints.py`** | Citizen draft submission, evidence upload validation, coordinate bounds, path traversal protection | 29 | 27.97s | **PASSED** | SQLite in-memory |
| **Total** | **Comprehensive Staging Regression** | **55 tests + 1 self-check** | **53.29s** | **100% PASS** | **0 Live MySQL Interactions** |

---

## 7. Compliance with Safety Rules

| Safety Constraint | Requirement | Status | Verification Evidence |
| :--- | :--- | :---: | :---: |
| **No Git Initialization** | Do not run `git init` in staging folder | **COMPLIED** | Staging folder contains no `.git` directory |
| **No Git Mutations** | No commit, push, stage, reset, clean | **COMPLIED** | `git status` in `C:\ThirdEye` remains untouched (19 modified, 16 untracked) |
| **No Remote / GitHub Changes** | Do not change remotes or settings | **COMPLIED** | Zero network or GitHub CLI commands executed |
| **No Live Database Access** | Do not query or modify live MySQL | **COMPLIED** | `mysql.connector.connect` patched to fail; SQLite dialect enforced |
| **No Source Modifications** | If a problem requires code changes, report and stop | **COMPLIED** | Hardcoded path issue reported without altering source code |
| **Dual Folder Preservation** | Keep `C:\ThirdEye` and staging folder intact | **COMPLIED** | Both folders completely preserved |

---

## 8. Summary of Unresolved Issues & Recommendations

### Unresolved Issue: Hardcoded Paths in Phase 6 Test Files
- **Affected Files:**
  - `test_phase6_1_csrf_security.py` (Line 44)
  - `test_phase6_2_config_security.py` (Line 50)
- **Problem:** `PROJECT_ROOT = r"C:\ThirdEye"` forces test execution to read from the original developer folder and prevents true standalone portability.
- **Proposed Fix (for future authorization):**
  Replace:
  ```python
  PROJECT_ROOT = r"C:\ThirdEye"
  ```
  With:
  ```python
  PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
  ```
- **Current Action:** Reported as an open finding per constraint instructions; no source edits performed.
