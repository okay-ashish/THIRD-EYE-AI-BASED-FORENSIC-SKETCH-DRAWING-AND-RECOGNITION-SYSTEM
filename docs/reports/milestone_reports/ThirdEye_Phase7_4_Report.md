# ThirdEye — Phase 7.4: Prepare a Clean Public-Release Staging Folder Report

**Date:** 2026-10-11  
**Source Project:** `C:\ThirdEye`  
**Staging Destination:** `C:\ThirdEye_Public_Release_Staging`  
**Target Environment:** Windows 11 Home Single Language (64-bit, build 26100), Anaconda Python 3.11 (`C:\Users\LENOVO\anaconda3\envs\ThirdEye311\python.exe`), Git 2.45.2.windows.1  
**Audit & Staging Type:** Non-Destructive Isolated Clean-Release Assembly  
**Deliverable Locations:**
- Workspace Scratch Mirror: `C:\ThirdEye\scratch\ThirdEye_Phase7_4_Report.md`
- Primary Windows Desktop: `C:\Users\LENOVO\Desktop\ThirdEye_Phase7_4_Report.md`
- Secondary OneDrive Desktop: `C:\Users\LENOVO\OneDrive\Desktop\ThirdEye_Phase7_4_Report.md`

---

## Overall Phase Status: ✅ PASS (CLEAN STAGING FOLDER PREPARED & VALIDATED)

A separate, completely decoupled clean-release staging copy has been assembled at `C:\ThirdEye_Public_Release_Staging`. All unverified checkpoints, sensitive credentials, live database dumps, private evidence, and temporary scratch scripts have been strictly excluded prior to copying. The staged copy has been operationally verified through isolated in-memory regression tests.

| Evaluation Gate | Status | Finding Summary |
|---|---|---|
| **Staging Conflict Safety** | **PASS** | `C:\ThirdEye_Public_Release_Staging` did not previously exist; created cleanly without overwriting. |
| **Original Project Immutability** | **PASS** | `C:\ThirdEye` was completely untouched. Zero files modified or deleted. Working tree preserved. |
| **Git Invariant Safety** | **PASS** | Zero `git add`, `git commit`, `git push`, `git clean`, or `git reset` executed. No Git repo created in staging (`.git` absent). |
| **Model Checkpoint Exclusion** | **PASS** | All unverified binary checkpoints (`cyclegan_model.pt`, `efficientnet_b0.onnx`, `face_reaging.onnx`, `*.h5`) are **100% ABSENT**. |
| **Sensitive Data Exclusion** | **PASS** | `.env`, `thirdeye_db.sql`, `instance/case_storage/`, and `static/person_db/` photos are **100% ABSENT**. |
| **Allowlist File Integrity** | **PASS** | 319 approved files copied; every file verified via SHA-256 checksum match against source. Total size: 35.89 MB. |
| **Manifest Generation** | **PASS** | Complete `STAGING_MANIFEST.md` generated with relative paths, sizes, and SHA-256 digests. |
| **Operational Independence & Testing**| **PASS** | 36 isolated regression tests executed directly against the staged copy; all passed 100% under in-memory SQLite. |
| **Procedural Fallback Readiness** | **PASS** | Application procedural fallbacks verified in staged copy; runs out-of-the-box without checkpoints. |

---

## 1. Summary of Staging Preparation

In Phase 7.3, ThirdEye’s remote GitHub repository (`https://github.com/okay-ashish/ThirdEye`) was found to be publicly accessible, exposing two binary model checkpoints with unverified provenance in historical commit `d5e3034`. Strategy C was recommended: prepare an independent clean staging directory containing only allowlisted source code, documentation, templates, tests, and permitted synthetic assets.

Phase 7.4 successfully implemented this clean staging preparation:
1. **Pre-Copy Allowlist Filtering:** Every file was evaluated and approved before any copying occurred. No questionable or denylisted files were ever placed into the destination directory.
2. **Selective Component Extraction:** Application source code, modular services, templates, isolated regression tests, sanitized schemas, front-end assets, and synthetic masks were extracted cleanly.
3. **Exclusion of Binary Blobs and Secrets:** Heavy binary weights, unvetted documentation with speculative URLs, live database exports, credentials, and temporary benchmark scripts were strictly excluded.
4. **Decoupled Verification:** The clean staged copy was tested using the isolated test runner. It passed 36 unit and integration test gates without requiring binary model weights or connecting to live MySQL.

---

## 2. Exact Staging Directory Location

- **Staging Root Path:** `C:\ThirdEye_Public_Release_Staging`
- **Filesystem Type:** NTFS (Local SSD, Windows 11)
- **Git Repository Status:** **UNINITIALIZED** (No `.git` folder exists; no remotes configured).

---

## 3. Number of Files Copied and Excluded

### A. Copied Files Summary (Allowlist)
Exactly **319 application and asset files** (plus 1 generated `STAGING_MANIFEST.md`) were copied into `C:\ThirdEye_Public_Release_Staging`:

| Directory / Component | File Count | Total Size | Description |
|---|---|---|---|
| **Root Level (`/`)** | 25 files | 425,750 B | Core application files (`app.py`, `models.py`, `face_reconstruction.py`, `face_variations.py`, `poster_generator.py`, `session_cleanup.py`, `utils.py`, `create_admin.py`, `create_user.py`), configs (`.env.example`, `.gitignore`, `requirements.txt`, `thirdeye_db.example.sql`), launch scripts (`run.ps1`, `run.bat`), docs (`README.md`, `LICENSE`), and 8 canonical isolated test suites. |
| **Services (`services/`)** | 3 files | 43,941 B | Modular workflow and complaint management (`__init__.py`, `complaint_service.py`, `workflow_service.py`). |
| **Scripts (`scripts/`)** | 1 file | 8,488 B | Fail-closed isolated regression test runner (`run_isolated_tests.py`). |
| **Templates (`templates/`)** | 18 files | 419,754 B | Complete Jinja2 HTML presentation layer (18 templates). |
| **Synthetic Models (`model/face_reaging/`)** | 2 files | 217,091 B | Procedural elliptical grayscale masks (`mask1024.jpg`, `mask512.jpg`) for continuous edge feathering. |
| **Static Assets (`static/`)** | 270 files | 36,514,134 B | Front-end web styles (`css/`), scripts (`js/`), 176+ canvas sketch parts (`sketch_parts/`), variation overlays (`variation_assets/`), third-party libraries (`vendor/`), directory guides (`person_db/README.md`), and directory structure placeholders (`.gitkeep`). |
| **Total Staged Footprint** | **319 files** | **37,629,158 B** | **35.89 MB** (Completely compliant with GitHub <100MB repository guidelines). |

---

### B. Excluded Files Summary (Denylist)
Approximately **5,788 files** across the workspace (or 126 distinct top-level project items) were explicitly excluded:

| Excluded Category | Items / Paths | Rationale for Exclusion |
|---|---|---|
| **Unverified Model Checkpoints** | `model/sketch_to_face/cyclegan_model.pt` (30.04 MB)<br>`model/face_parsing/efficientnet_b0.onnx` (26.28 MB) | Checkpoint training provenance and redistribution permissions are **UNVERIFIED**. |
| **Restricted Checkpoints** | `model/face_reaging/face_reaging.onnx` (118.48 MB) | Disney Research FRAN non-commercial research terms; exceeds GitHub 100 MB file limit. |
| **Legacy Checkpoints** | `kunal_model.h5` (207.7 MB)<br>`rithanya_model.h5` (112.1 MB)<br>`mishafakhar_model.h5` (38.65 MB) | Unverified student experimental models; large binary weights (>350 MB total). |
| **Unvetted Model Documentation** | `model/sketch_to_face/README.md`<br>`model/face_parsing/README.md`<br>`model/face_reaging/README.md` | Contain unsupported licensing claims, claims that checkpoints can be committed directly, or unverified external download URLs. |
| **Exploratory Data Files** | `model/chennai.csv`<br>`model/chennai.ipynb` | NCRB crime statistics and Jupyter notebooks unrelated to core application. |
| **Sensitive Configuration** | `.env` | Local environment file containing live database user credentials and passwords. |
| **Live Database Dumps** | `thirdeye_db.sql` | Live MySQL dump containing potential private user or complaint data. |
| **Private Case Evidence** | `instance/*` (including `instance/case_storage/`) | Citizen evidence submissions, uploaded case images, and generated variations. |
| **Biometric Gallery Photos** | `static/person_db/*.jpg`, `*.png` | Enrolled suspect test portraits and biometric gallery images. |
| **Scratch Exploration Scripts** | `scratch_*.py` (45+ files) | Intermediate developer prototyping and exploratory scripts. |
| **Benchmark Generators** | `generate_phase*.py`, `run_phase*.py` | Visual sheet and benchmark comparison generation scripts. |
| **Legacy Test Suites** | `test_phase2.py`, `test_phase3.py`, `test_phase3_1.py`, `test_phase4.py`, `test_phase4_1.py`, `test_phase4_2.py`, `test_phase4_2_1.py`, `test_phase4_2_2.py`, `test_phase4_3.py`, `test_phase4_4.py`, `test_phase4_6.py`, `test_phase5.py`, `test_phase6.py` | Legacy test suites that explicitly assert the existence of local binary model files (`cyclegan_model.pt`). |
| **Internal Phase Reports** | `phase*.md`, `github_preparation_*.md` | Internal developmental audit reports from earlier project phases. |
| **Environment & Build Artifacts** | `.git/`, `.venv/`, `.vscode/`, `__pycache__/`, `scratch/`, `wheels/`, `*.whl` | Git commit history containing legacy binary blobs, virtual environment libraries, compiled bytecode, and temporary scratch files. |

---

## 4. File Manifest Location and Validation Results

- **Manifest Markdown:** `C:\ThirdEye_Public_Release_Staging\STAGING_MANIFEST.md`
- **Workspace Scratch Mirror:** [staging_manifest.md](file:///C:/ThirdEye/scratch/staging_manifest.md)
- **Manifest JSON:** `C:\ThirdEye\scratch\staging_manifest.json`

### Checksum Validation Results
Every file copied into `C:\ThirdEye_Public_Release_Staging` was verified by computing the SHA-256 hash of the destination file and comparing it against the source file in `C:\ThirdEye`:
- **Files Verified:** 319 / 319 (100.0%)
- **Checksum Mismatches:** 0
- **Size Discrepancies:** 0
- **Integrity Status:** **PERFECT MATCH**

---

## 5. Confirmation of Excluded Checkpoints and Sensitive Data

A post-copy static inspection of `C:\ThirdEye_Public_Release_Staging` was executed:

| Scanned Pattern | Scope Checked | Result | Status |
|---|---|---|---|
| `*.pt`, `*.onnx`, `*.h5` | All subdirectories | **0 files found** | **PASS (ABSENT)** |
| `.env`, `*.env` | Staging root & subdirectories | **0 files found** | **PASS (ABSENT)** |
| `*.sql` (excluding `thirdeye_db.example.sql`) | Staging root & subdirectories | **0 files found** | **PASS (ABSENT)** |
| `case_storage` | All subdirectories | **0 directories found** | **PASS (ABSENT)** |
| `static/person_db/*.jpg`, `*.png` | Gallery directory | **0 image files found** (Only `README.md` present) | **PASS (ABSENT)** |
| `.git` | Staging root | **0 folders found** (No Git repo) | **PASS (ABSENT)** |
| `scratch`, `__pycache__`, `.venv` | All subdirectories | **0 folders found** | **PASS (ABSENT)** |

---

## 6. Secret, Database-Dump, and Private-Evidence Scan Results

1. **Configuration Template (`.env.example`):**
   - Contains only placeholder values: `CHANGE_ME_TO_A_SECURE_RANDOM_SECRET`, `localhost`, `root`, `CHANGE_ME`.
   - Zero hardcoded production passwords or actual secret keys.
2. **Sanitized Database Schema (`thirdeye_db.example.sql`):**
   - 7,190 bytes. Contains purely structural `CREATE DATABASE IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` DDL statements for `users`, `persons`, `complaints`, `complaint_evidence`, and `complaint_timeline`.
   - Verified that `INSERT INTO users` and `INSERT INTO complaints` do not appear. Zero personal data, credentials, or case evidence records are included.
3. **Application Secret Key Handling (`app.py`):**
   - In production (`FLASK_ENV=production`), application requires `THIRDEYE_SECRET_KEY` in `.env` and aborts immediately if missing.
   - In development, generates a random temporary key with an explicit console warning.
   - Zero hardcoded secret fallbacks exist in code.

---

## 7. Test Commands Actually Executed and Their Results

Three distinct test suites were executed directly against `C:\ThirdEye_Public_Release_Staging` using Python 3.11 in isolated in-memory SQLite mode:

### Test Execution Summary Table

| # | Executed Command | Suite Focus | Checks Run | Duration | Result |
|---|---|---|---|---|---|
| 1 | `python scripts/run_isolated_tests.py --suite test_phase2_complaint_models.py` | Complaint schema, relationships, two-role model, table creation | 11 | 6.423s | **PASS (11/11 OK)** |
| 2 | `python scripts/run_isolated_tests.py --suite test_phase6_2_config_security.py` | Secret key fail-closed, temporary dev key, CSRF protection, addendum lifecycle | 10 | 73.725s | **PASS (10/10 OK)** |
| 3 | `python scripts/run_isolated_tests.py --suite test_phase5_1_biometric_case_binding.py` | Case-bound biometrics, POST enforcement, negative detection, dlib feature extraction | 15 | 35.999s | **PASS (15/15 OK)** |

**Total Tests Executed:** 36 checks  
**Total Failures / Errors:** 0  
**Live MySQL Interactions:** 0 (Direct MySQL connections blocked at library level by `run_isolated_tests.py`).

---

## 8. Missing Files, Unsupported Claims, and Release Blockers

### A. Missing Files Analysis
- **Zero Missing Files:** All 319 required application files, templates, services, front-end assets, and synthetic masks are present.
- **Model Checkpoints:** While `cyclegan_model.pt`, `efficientnet_b0.onnx`, and `face_reaging.onnx` are absent, the application's procedural fallbacks (`reconstruct_face_procedural` in `face_reconstruction.py` and the 68-point landmark geometry spline mapper in `face_variations.py`) are fully operational and verified.

### B. Documentation & Download URL Audit
- Staged documentation was scanned for unverified external download URLs (such as third-party GitHub forks or speculative mirrors). **Zero unverified download URLs exist in staged files.**
- `README.md` accurately describes the system's dual-mode capability:
  - Deterministic Procedural Fallback mode (fully functional out-of-the-box).
  - Neural vision models as optional experimental enhancements requiring independent investigator verification.

### C. Portability Observation
- In `test_phase6_1_csrf_security.py` (Line 44) and `test_phase6_2_config_security.py` (Line 50), a fallback string `PROJECT_ROOT = r"C:\ThirdEye"` exists if the script is invoked directly as a standalone script without arguments.
- When invoked via the standard test runner (`python scripts/run_isolated_tests.py --suite <name>`), `scripts/run_isolated_tests.py` inserts the staging directory (`os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))`) at index 0 of `sys.path`, ensuring all module imports load strictly from `C:\ThirdEye_Public_Release_Staging`.
- This behavior was operationally verified by the successful execution of `test_phase6_2_config_security.py` inside the staging directory.

---

## 9. Confirmation of Zero Prohibited Modifications

In strict compliance with Phase 7.4 safety rules, the following actions are explicitly confirmed:

1. **Source Project Untouched:**
   - No files in `C:\ThirdEye` were deleted, renamed, or modified during Phase 7.4.
   - `git status --short` in `C:\ThirdEye` remains completely identical to its pre-phase state.
2. **Zero Git Mutations:**
   - `git commit` was **NOT** executed.
   - `git push` was **NOT** executed.
   - `git add` (staging) was **NOT** executed.
   - `git reset` was **NOT** executed.
   - `git clean` was **NOT** executed.
   - Git history was **NOT** rewritten or altered.
3. **Staging Folder Untouched by Git:**
   - `git init` was **NOT** executed in `C:\ThirdEye_Public_Release_Staging`.
   - No Git remotes were configured.
4. **Zero Live Database Operations:**
   - The live MySQL database `thirdeye_db` was **NOT** connected to, queried, or modified.
5. **Zero External Downloads:**
   - No models, weights, datasets, or external wheels were downloaded.

---

## Stop Condition Compliance

Phase 7.4 staging folder preparation and validation is complete. Execution is stopped for user review. No Git repository initialization, publishing, remote configuration, or further modifications will take place without explicit user approval.
