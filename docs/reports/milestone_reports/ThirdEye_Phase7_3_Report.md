# ThirdEye — Phase 7.3: Public Repository Exposure Assessment and Clean-Release Plan Report

**Date:** 2026-10-11  
**Project Root:** `C:\ThirdEye`  
**Target Environment:** Windows 11 Home Single Language (64-bit, build 26100), Anaconda Python 3.11 (`C:\Users\LENOVO\anaconda3\envs\ThirdEye311\python.exe`), Git 2.45.2.windows.1  
**Audit Type:** Read-Only Exposure Assessment & Remediation Architecture Plan  
**Deliverable Locations:**
- Workspace Scratch Mirror: `C:\ThirdEye\scratch\ThirdEye_Phase7_3_Report.md`
- Primary Windows Desktop: `C:\Users\LENOVO\Desktop\ThirdEye_Phase7_3_Report.md`
- Secondary OneDrive Desktop: `C:\Users\LENOVO\OneDrive\Desktop\ThirdEye_Phase7_3_Report.md`

---

## Overall Assessment Status: 🛑 RELEASE BLOCKED (ACTIVE PUBLIC EXPOSURE IDENTIFIED)

| Assessment Gate | Status | Finding Summary |
|---|---|---|
| **Remote Repository Visibility** | **BLOCKER (ACTIVE EXPOSURE)** | Remote `https://github.com/okay-ashish/ThirdEye` is **CONFIRMED PUBLIC**. Anonymously accessible without authentication. |
| **Model Checkpoint Exposure** | **BLOCKER (ACTIVE EXPOSURE)** | Both `cyclegan_model.pt` (30.04 MB) and `efficientnet_b0.onnx` (26.28 MB) are **publicly accessible and downloadable** via GitHub web blobs and `raw.githubusercontent.com` (HTTP 200). |
| **Model Checkpoint Provenance** | **BLOCKER** | Training dataset provenance and redistribution permissions for both exposed checkpoints are **UNVERIFIED**. |
| **Re-Aging Checkpoint Exposure** | **PASS** | `face_reaging.onnx` (118.48 MB) is **NOT EXPOSED** (HTTP 404 on GitHub). Never tracked or committed. |
| **Sensitive Data Exposure** | **PASS** | `.env`, `thirdeye_db.sql`, `instance/case_storage/`, and `static/person_db/` photos are **NOT EXPOSED** (HTTP 404 on GitHub). |
| **Procedural Fallback Independence** | **PASS** | Application architecture features built-in, verified procedural fallbacks for all three AI modules; can run completely without checkpoints. |
| **Clean-Release Plan** | **READY FOR REVIEW** | Comprehensive comparison of Strategies A–E prepared. Two-stage remediation recommended (Private toggle + Clean public repository). |

---

## 1. Executive Summary and Release-Readiness Decision

Phase 7.3 conducted a read-only assessment of ThirdEye’s remote GitHub exposure, reconciled all local model assets, analyzed historical tracking structures, and designed a safe release architecture. In strict compliance with Phase 7.3 safety constraints:
- **No Git write operations:** Zero commits, zero pushes, zero files staged (`git add`), zero resets, zero cleans, zero branch modifications, and zero history rewrites were performed.
- **No file alterations:** No source files, scripts, or model checkpoints were deleted, moved, renamed, or modified.
- **No database queries:** The live MySQL database `thirdeye_db` was not accessed, queried, or modified.
- **Local environment preserved:** All locally installed models remain intact; the application continues to run in the local Anaconda environment.

### Critical Finding & Release-Readiness Decision
**Decision: 🛑 RELEASE BLOCKED / NOT READY FOR PUBLIC RELEASE.**

1. **Active Anonymous Public Exposure:** Anonymous HTTP inspection confirmed that `https://github.com/okay-ashish/ThirdEye` is **ALREADY PUBLIC**.
2. **Binary Weights Are Downloadable:** Both `model/sketch_to_face/cyclegan_model.pt` (30.04 MB) and `model/face_parsing/efficientnet_b0.onnx` (26.28 MB) reside in commit `d5e3034` on `origin/main` and can currently be downloaded anonymously by anyone in the world via `raw.githubusercontent.com`.
3. **Unverified Checkpoint Provenance:** Neither checkpoint’s training dataset nor redistribution permission has been verified.
4. **Remediation Required:** Pushing any additional commits to `origin/main` without addressing commit `d5e3034` does not remove the historical blobs. A disciplined pre-release remediation plan must be selected and approved by the repository owner before a public release can be declared clean.

---

## 2. Verified Repository Visibility and Exposure Findings

An anonymous, read-only inspection was performed across the public network without using credentials or modifying local Git state:

### A. Repository-Level Visibility
- **Configured Remote URL:** `https://github.com/okay-ashish/ThirdEye.git`
- **Anonymous HTTP Access:** HTTP GET request to `https://github.com/okay-ashish/ThirdEye` succeeded anonymously with HTTP 200.
- **Page Title:** `<title>GitHub - okay-ashish/ThirdEye: ThirdEye is an AI-assisted forensic computer vision system for sketch construction, facial reconstruction, face recognition, appearance variation, photo-to-sketch conversion, and public-display poster generation. · GitHub</title>`
- **Repository Visibility:** **CONFIRMED PUBLIC** (Not private, not restricted).

### B. Remote References (`git ls-remote origin`)
- **Remote HEAD:** `d5e3034c83fee1fc39654e7988be6ca0ae6e8410`
- **Remote `refs/heads/main`:** `d5e3034c83fee1fc39654e7988be6ca0ae6e8410`
- **Remote Tags:** **NONE**. (Local tag `phase0-baseline-2026-10-10` was created locally and was **never pushed** to `origin`).

### C. Live Remote File Exposure Matrix

| Target Remote Path | Test Method | HTTP Status | Exposure Finding |
|---|---|---|---|
| `model/sketch_to_face/cyclegan_model.pt` (Web Blob) | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/model/sketch_to_face/cyclegan_model.pt` | **200 OK** | **PUBLICLY EXPOSED** |
| `model/sketch_to_face/cyclegan_model.pt` (Raw Content) | HTTP HEAD on `https://raw.githubusercontent.com/okay-ashish/ThirdEye/main/model/sketch_to_face/cyclegan_model.pt` | **200 OK** | **DOWNLOADABLE ANONYMOUSLY** |
| `model/face_parsing/efficientnet_b0.onnx` (Web Blob) | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/model/face_parsing/efficientnet_b0.onnx` | **200 OK** | **PUBLICLY EXPOSED** |
| `model/face_parsing/efficientnet_b0.onnx` (Raw Content) | HTTP HEAD on `https://raw.githubusercontent.com/okay-ashish/ThirdEye/main/model/face_parsing/efficientnet_b0.onnx` | **200 OK** | **DOWNLOADABLE ANONYMOUSLY** |
| `model/face_reaging/face_reaging.onnx` | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/model/face_reaging/face_reaging.onnx` | **404 Not Found** | **SAFE (NOT EXPOSED)** |
| `.env` (Application Secrets) | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/.env` | **404 Not Found** | **SAFE (NOT EXPOSED)** |
| `thirdeye_db.sql` (Live Database Dump) | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/thirdeye_db.sql` | **404 Not Found** | **SAFE (NOT EXPOSED)** |
| `instance/case_storage/` | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/instance/case_storage` | **404 Not Found** | **SAFE (NOT EXPOSED)** |
| `static/person_db/test_person.jpg` | HTTP HEAD on `https://github.com/okay-ashish/ThirdEye/blob/main/static/person_db/test_person.jpg` | **404 Not Found** | **SAFE (NOT EXPOSED)** |

---

## 3. Git History and Checkpoint-Tracking Analysis

### A. Commit Graph Structure
The repository contains exactly **1 commit** across all local and remote branches:
- Commit Hash: `d5e3034c83fee1fc39654e7988be6ca0ae6e8410`
- Author: Ashish `<kumarashish3062005@gmail.com>`
- Date: `Tue Oct 6 21:04:57 2026 +0530`
- Subject: `"Initial commit: ThirdEye AI-assisted forensic facial analysis and reconstruction system"`
- Parent Commits: None (Root commit).
- Direct Blobs in Commit Tree:
  - `model/sketch_to_face/cyclegan_model.pt` (blob `7c65d6...`, 31,495,009 bytes)
  - `model/face_parsing/efficientnet_b0.onnx` (blob `e38f1a...`, 27,560,383 bytes)

### B. References Pointing to Commit `d5e3034`
1. Local `refs/heads/main`
2. Remote-tracking `refs/remotes/origin/main`
3. Remote `refs/heads/main` on GitHub
4. Local tag `refs/tags/phase0-baseline-2026-10-10`

### C. Comprehensive Asset Tracking & Exposure Matrix

| Asset Path | 1. In Local Directory? | 2. In Current Index? | 3. In Current Commit? | 4. In Reachable History? | 5. In Public Remote Ref? | 6. Public Exposure Status |
|---|---|---|---|---|---|---|
| `model/sketch_to_face/cyclegan_model.pt` | **YES** | **YES** | **YES** (`d5e3034`) | **YES** (`d5e3034`, tag) | **YES** (`origin/main`) | **CONFIRMED PUBLIC EXPOSURE** |
| `model/face_parsing/efficientnet_b0.onnx` | **YES** | **YES** | **YES** (`d5e3034`) | **YES** (`d5e3034`, tag) | **YES** (`origin/main`) | **CONFIRMED PUBLIC EXPOSURE** |
| `model/face_reaging/face_reaging.onnx` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `model/face_reaging/mask1024.jpg` | **YES** | **YES** | **YES** (`d5e3034`) | **YES** (`d5e3034`, tag) | **YES** (`origin/main`) | **CONFIRMED PUBLIC (PERMITTED SYNTHETIC)** |
| `model/face_reaging/mask512.jpg` | **YES** | **YES** | **YES** (`d5e3034`) | **YES** (`d5e3034`, tag) | **YES** (`origin/main`) | **CONFIRMED PUBLIC (PERMITTED SYNTHETIC)** |
| `model/sketch_to_face/kunal_model.h5` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `model/sketch_to_face/rithanya_model.h5` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `model/sketch_to_face/mishafakhar_model.h5` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `.env` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `thirdeye_db.sql` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `instance/case_storage/*` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |
| `static/person_db/*.jpg` | **YES** | **NO** (Ignored) | **NO** | **NO** | **NO** | **NOT EXPOSED (SAFE)** |

---

## 4. Reconciled Model Inventory and Checksums

All model files on disk were re-evaluated using Python read-only streaming SHA-256 computation:

### A. Reconciled Inventory Table

| Local Model Path | Exact Byte Size | Size in MB | Current SHA-256 Digest | Status & Tracking |
|---|---|---|---|---|
| `model/sketch_to_face/cyclegan_model.pt` | 31,495,009 bytes | 30.04 MB | `68aee9c65c90cab94c67e32a7bf212b4f278df77677f5e8c295e06a45376ff6a` | Tracked in Git / Publicly Exposed |
| `model/face_parsing/efficientnet_b0.onnx` | 27,560,383 bytes | 26.28 MB | `2968268aa886a4ba296f6017a332d60640bb2ec6797ae4d528a50736ff5a6431` | Tracked in Git / Publicly Exposed |
| `model/face_reaging/face_reaging.onnx` | 124,230,760 bytes | 118.48 MB | `62c62598a71067cf12680c8421230556d08069d172f1dc645be2a5ebe815fb1f` | Untracked / Protected by `.gitignore` |
| `model/sketch_to_face/kunal_model.h5` | 217,820,864 bytes | 207.73 MB | `3536d9341014426b6488e885ac4574b96049663ed949b63298c46b7a7cce87b8` | Untracked / Protected by `*.h5` |
| `model/sketch_to_face/rithanya_model.h5` | 117,564,288 bytes | 112.12 MB | `dd14edf64480f8f4ab565335ba9663994966038740f0f4f67c6570e181bf3dc2` | Untracked / Protected by `*.h5` |
| `model/sketch_to_face/mishafakhar_model.h5` | 40,527,792 bytes | 38.65 MB | `352e9a14ff36d4cef93348eecb5b8d2b281511e0316020bbfcc44af1a943b198` | Untracked / Protected by `*.h5` |
| `model/face_reaging/mask1024.jpg` | 206,556 bytes | 0.20 MB | `d28fcdfd77b6d22c24153fbea0ea39b84cc967063fbeeee9389e1513e8ba8565` | Tracked in Git / Synthetic Mask |
| `model/face_reaging/mask512.jpg` | 10,535 bytes | 0.01 MB | `062526a2a4d73c91f06c90059a78d48e46a5dc7c73a5652175c42c3a4ad635c3` | Tracked in Git / Synthetic Mask |

### B. Reconciliation of the FRAN Size Discrepancy
- **Reported in Phase 7.1:** `124,233,728` bytes (118.48 MB)
- **Reported in Phase 7.2:** `124,230,760` bytes (118.48 MB)
- **Current Physical Measurement:** `124,230,760` bytes (118.4757 MB)
- **File System Evidence:**
  - `os.stat('model/face_reaging/face_reaging.onnx').st_mtime`: `2026-10-01 08:41:30.874318`
  - `os.stat('model/face_reaging/face_reaging.onnx').st_ctime`: `2026-10-01 08:41:17.448905`
  - The physical file on disk was created and last modified on **October 1, 2026**, nine days prior to Phase 7 and Phase 7.1. It has never been modified or replaced since creation.
- **Root Cause Determination:** The `124,233,728` bytes figure in the Phase 7.1 report was a **documentation recording inconsistency** (a 2,968-byte discrepancy, likely introduced by an approximate binary formula or documentation typo in Phase 7.1). The exact byte size of `face_reaging.onnx` is, and has remained, **124,230,760 bytes**.

---

## 5. Clean-Release Content Boundary (Allowlist vs. Denylist)

To guarantee that any future public release contains only safe, unencumbered, auditable source code without sensitive data or unverified binary checkpoints, the following boundary is established:

### A. Proposed Clean-Release Allowlist

| Category | Allowlisted Paths / Patterns | Description & Provenance |
|---|---|---|
| **Core Source Code** | `app.py`, `models.py`, `face_reconstruction.py`, `face_variations.py`, `poster_generator.py`, `session_cleanup.py`, `utils.py`, `create_admin.py`, `create_user.py` | Complete ThirdEye Python application logic and administrative entry points. |
| **Modular Services** | `services/audit_service.py`, `services/case_service.py`, `services/evidence_service.py`, `services/workflow_service.py` | Modular service abstractions implementing complaint workflow, timeline auditing, and evidence binding. |
| **Execution Scripts** | `scripts/run_isolated_tests.py`, `run.ps1`, `run.bat` | Verified test runners and platform launch scripts. |
| **HTML Templates** | `templates/*.html` (18 templates) | Complete Bootstrap 5 / Jinja2 front-end presentation layer. |
| **Automated Regressions** | `test_phase2_complaint_models.py`, `test_phase3_complaints.py`, `test_phase4_workflow.py`, `test_phase5_forensic_artifacts.py`, `test_phase5_1_biometric_case_binding.py`, `test_phase6_security_reliability.py`, `test_phase6_1_csrf_security.py`, `test_phase6_2_config_security.py` | Isolated, fail-closed regression test harness. |
| **Static Web Assets** | `static/css/*`, `static/js/*`, `static/canvas_assets/*` (176+ composite sketch SVG/PNG parts), `static/person_db/README.md` | Front-end styles, interactive canvas constructor components, and directory usage guide. |
| **Synthetic Visual Assets** | `model/face_reaging/mask1024.jpg`, `model/face_reaging/mask512.jpg` | Procedural elliptical grayscale masks created for continuous edge boundary alpha feathering. Contains no human biometric data. |
| **Model Documentation** | `model/sketch_to_face/README.md`, `model/face_parsing/README.md`, `model/face_reaging/README.md` | Architectural documentation and model directory layout instructions. |
| **Sanitized Configuration** | `.env.example`, `thirdeye_db.example.sql`, `requirements.txt`, `LICENSE` (MIT), `README.md` | Sanitized templates, DDL schema, pinned dependency specifications, and verified documentation. |

---

### B. Proposed Clean-Release Denylist

| Category | Denylisted Paths / Patterns | Risk & Reason for Absolute Exclusion |
|---|---|---|
| **Application Secrets** | `.env`, `*.env` | Live credentials, local database passwords, and cryptographic secrets. |
| **Live Database Dumps** | `thirdeye_db.sql`, `*.sql` (except `thirdeye_db.example.sql`) | Live schema exports or potential citizen personal data dumps. |
| **Private Case Storage** | `instance/case_storage/*`, `instance/*` | Uploaded evidence photos, citizen statements, and generated case variations. |
| **Biometric Gallery Data** | `static/person_db/*.jpg`, `static/person_db/*.png` | Enrolled suspect portraits and test facial imagery. |
| **Unverified Checkpoints** | `model/sketch_to_face/cyclegan_model.pt` | 30.04 MB. Checkpoint training provenance and redistribution rights are **UNVERIFIED**. |
| **Unverified / Restricted** | `model/face_parsing/efficientnet_b0.onnx` | 26.28 MB. Checkpoint training provenance is **UNVERIFIED**; upstream workflow cites CelebAMask-HQ non-commercial dataset. |
| **Restricted Checkpoints** | `model/face_reaging/face_reaging.onnx` | 118.48 MB. Disney Research FRAN non-commercial terms; exceeds GitHub 100 MB file limit. |
| **Legacy H5 Checkpoints** | `model/sketch_to_face/*.h5` | 375 MB total (`kunal_model.h5`, `rithanya_model.h5`, `mishafakhar_model.h5`). Unverified student experimental checkpoints. |
| **Scratch Files & Reports** | `scratch/*`, `scratch_*.py` | Scratch test scripts, temporary benchmarks, and internal phase audit reports. |
| **Binary Wheels & Builds** | `wheels/*`, `*.whl`, `__pycache__/*`, `.venv/*` | Binary wheels and environment build artifacts. |
| **Prototype Directories** | `prototype_eval/*`, `scratch_clean_wigs/*` | Intermediate prototyping folders and temporary asset generation scratchpads. |

---

## 6. Comprehensive Comparison of Remediation Strategies

| Strategy | Description & Mechanism | Impact on Local Working Tree & Models | What Happens to Historical Git References / Blobs | Security & Licensing Efficacy | Collaboration / Downstream Risks | Approval Required | Meets Clean Public Release Goal? |
|---|---|---|---|---|---|---|---|
| **Strategy A:** Remove checkpoints in a new commit (`git rm --cached`) | Untrack `cyclegan_model.pt` and `efficientnet_b0.onnx` via `git rm --cached`, update `.gitignore`, and commit changes forward on `main`. | **Zero impact.** Files remain in `C:\ThirdEye\model\`. Local app continues running without interruption. | **Blobs remain in commit `d5e3034`!** Anyone cloning full Git history or browsing commit `d5e3034` on GitHub still downloads both checkpoints (~56.3 MB). | **POOR / PARTIAL.** Stops future tracking, but leaves historical binaries publicly exposed. | None. Standard forward commit. | Repository Owner | **NO.** Fails clean release standard because unverified checkpoints remain in Git history. |
| **Strategy B:** Create a clean orphan branch (`git checkout --orphan`) | Create an unparented branch `clean-release`, stage only allowlisted files, commit, push, and set as default branch on GitHub. | **Zero impact.** Local working tree and model files are preserved. | **Commit `d5e3034` STILL EXISTS on GitHub!** Branch `main` and commit `d5e3034` remain accessible via branch selector, commit SHA, or Git clone. | **MISLEADING / INCOMPLETE.** Presents clean front-end UI on branch `clean-release`, but repository retains weights in history. | Users cloning with `--all` or inspecting `main` still download checkpoints. | Repository Owner | **NO.** Cannot be described as complete historical removal unless `main` is deleted and GC purged. |
| **Strategy C:** Prepare a separate clean public repository | Initialize a completely new, clean Git repository in a distinct staging directory; copy only allowlisted files; verify hashes; publish as initial commit of new repo. | **Zero impact.** Current `C:\ThirdEye` workspace remains completely untouched as private development tree. | **100% clean Git history from commit 0.** Zero legacy baggage, zero historical checkpoint blobs, zero exposure. Existing repo can be made private. | **EXCELLENT / OPTIMAL.** Guaranteed zero unverified binaries or historical leakages in public repository. | High risk of human error during manual file copy if not automated via strict allowlist script. | Project Owner (to create new repo or replace remote) | **YES (RECOMMENDED).** Meets highest standard of clean public open-source release. |
| **Strategy D:** Remediate existing repository history (`git-filter-repo`) | Use `git-filter-repo` to rewrite commit `d5e3034` into a new initial commit excluding both model blobs; force-push (`git push --force origin main`). | **Zero impact on files**, but local Git commit hashes are rewritten. | Removes both checkpoint blobs from commit history across all branches and tags. | **GOOD**, but GitHub retains orphaned commit objects in back-end cache until reflog/GC runs (requires GitHub Support). | **DESTRUCTIVE.** Rewrites commit SHAs; breaks forks, existing clones, and collaborator pull requests with non-fast-forward errors. | Explicit Project Owner written consent | **POTENTIALLY**, but carries high operational disruption and GitHub cache retention risks. |
| **Strategy E:** Temporarily make existing repository private | Change repository visibility in GitHub settings from Public to Private (`Settings -> Danger Zone -> Change visibility`). | **Zero impact.** Working tree and Git state unaffected. | No change to Git history or commits. Immediately disables public web and anonymous API access to all files. | **IMMEDIATE CONTAINMENT.** Immediately cuts off ongoing anonymous public downloads of `cyclegan_model.pt` and `efficientnet_b0.onnx`. | Does not undo copies already cloned or downloaded by external parties in the past. | Repository Owner GitHub Account Admin | **NO on its own**, but **CRITICAL as Immediate Step 1** before Strategy C or D. |

---

## 7. Operational Requirements for a Clean Release

To ensure that a clean checkout from a public repository functions predictably and honestly without silently depending on unverified binary checkpoints:

### A. Fallback Autonomy (Code Review Findings)
An exhaustive inspection of ThirdEye’s core vision modules revealed that **the application already possesses robust, deterministic procedural fallbacks that require zero code modifications**:
1. **Sketch Reconstruction (`face_reconstruction.py`):**
   - If `cyclegan_model.pt` is absent, `get_sketch_to_face_model()` returns `None`.
   - The engine automatically activates `reconstruct_face_procedural()` with Fitzpatrick skin tone color grading and landmark boundary integration.
   - The UI template `reconstructed_face.html` correctly displays: `Engine: Procedural Fallback` (yellow badge).
2. **Semantic Face Parsing (`face_variations.py`):**
   - If `efficientnet_b0.onnx` is absent, `get_face_parser_session()` returns `None`.
   - The engine automatically falls back to the 68-point Anthropometric Landmark Geometry Spline Mapper (`build_anatomical_region_map` landmark fallback) without error.
3. **Face Re-Aging (`face_variations.py`):**
   - If `face_reaging.onnx` is absent, `get_fran_session()` returns `None`.
   - The engine automatically falls back to `_apply_procedural_age_adjustment` (Phase 4.3 anatomical age engine).
4. **Biometric Face Recognition (`app.py`, `face_recognition`):**
   - Extracts 128-D biometric embeddings via standard pip package `face_recognition_models`.
   - Requires zero model files inside the ThirdEye repository directory.

### B. Documentation Requirements for Clean Release
1. **Explain Fallback Mechanics in `README.md`:** The README must clearly state that ThirdEye operates in a fully functional **Deterministic Procedural Mode** out-of-the-box, and that neural checkpoints are optional experimental enhancements.
2. **No Speculative Download Links:** The README must **not** provide unverified third-party download scripts or unofficial mirror links for `cyclegan_model.pt` or `efficientnet_b0.onnx`.
3. **Sanitized Database Setup:** Clearly document `thirdeye_db.example.sql` and `create_admin.py` without referring to private database dumps.
4. **Secret Key Hardening:** Clearly document that `THIRDEYE_SECRET_KEY` must be configured in `.env` for production, and that omitting it in production triggers an intentional fail-closed startup abort.

---

## 8. Required Approvals and Remaining Blockers

### A. Release Blockers
1. **BLOCKER 1: Active Public Exposure of Binary Checkpoints.**
   - Both `model/sketch_to_face/cyclegan_model.pt` and `model/face_parsing/efficientnet_b0.onnx` are live and anonymously downloadable on GitHub at `https://github.com/okay-ashish/ThirdEye`.
2. **BLOCKER 2: Unverified Checkpoint Provenance.**
   - The training datasets and redistribution rights for ThirdEye’s exact local checkpoint files remain unverified.
3. **BLOCKER 3: Historical Persistence in Commit `d5e3034`.**
   - Pushing simple forward commits on `main` does not remove historical blobs from `d5e3034`.

### B. Required Approvals
- **Approval 1 (Containment):** Owner approval to toggle `okay-ashish/ThirdEye` to **Private** on GitHub.
- **Approval 2 (Remediation Selection):** Owner decision between **Strategy C** (Separate clean public repository) and **Strategy D** (History rewrite via `git-filter-repo`).

---

## 9. Recommended Next Steps with Risks and Consequences

### Recommended Two-Stage Remediation Path

```
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Immediate Risk Containment (Strategy E)             │
│ - Change https://github.com/okay-ashish/ThirdEye to PRIVATE │
│ - Halts anonymous downloads of unverified checkpoints        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Clean Public Release Preparation (Strategy C)       │
│ - Staging directory populated strictly via Allowlist script │
│ - Automated scan for secrets, dumps, photos, and weights    │
│ - Push clean commit 0 to new public repo (e.g. ThirdEye)    │
│ - Existing C:\ThirdEye preserved intact as private workspace │
└─────────────────────────────────────────────────────────────┘
```

### Risks and Consequences Analysis
1. **Why Stage 1 First:**
   - Setting the repository to Private requires approximately 30 seconds in GitHub Settings.
   - It immediately eliminates the active anonymous exposure of `cyclegan_model.pt` and `efficientnet_b0.onnx` without requiring any local code or Git modifications.
   - *Limitation:* It does not undo past downloads, but prevents further public distribution.
2. **Why Strategy C over Strategy D for Stage 2:**
   - **Strategy D (`git-filter-repo`) Risks:** Rewriting commit `d5e3034` changes the root commit SHA, requiring a force-push (`--force`). GitHub’s internal cache retains orphaned commits, and any external party who has already cloned the repo will experience Git history divergence errors.
   - **Strategy C (Clean New Repo) Benefits:** Starting with a fresh repository initialized from the allowlist guarantees that the public release has an immaculate Git history from commit 0, with zero binary weights, zero legacy commits, and zero cache retention issues.
   - **Local Environment Preservation:** The existing local workspace at `C:\ThirdEye` remains 100% operational, retaining all installed model checkpoints, experimental scripts, and database configurations for local academic demonstrations.

---

## 10. Exact Inspection Commands Executed and Outcomes

| # | Command Executed | Working Purpose | Exit Code / Outcome |
|---|---|---|---|
| 1 | `git branch -a -v` | Inspect local and remote-tracking branch references | Code 0: `main` and `origin/main` both point to `d5e3034` |
| 2 | `git tag -l` | Check for local tag references | Code 0: `phase0-baseline-2026-10-10` found |
| 3 | `git show-ref --tags` | Verify commit pointed to by tag | Code 0: Points to `d5e3034c83fee1fc39654e7988be6ca0ae6e8410` |
| 4 | `git remote -v` | Inspect remote URLs without modification | Code 0: `origin` points to `https://github.com/okay-ashish/ThirdEye.git` |
| 5 | `git ls-remote origin` | Query remote repository refs read-only | Code 0: Remote HEAD and `refs/heads/main` at `d5e3034`; 0 remote tags |
| 6 | Anonymous HTTP request to `https://github.com/okay-ashish/ThirdEye` | Verify public repository visibility anonymously | Code 0: HTTP 200 OK; repository is publicly accessible |
| 7 | Anonymous HTTP HEAD on `cyclegan_model.pt` blob & raw URLs | Check public exposure of CycleGAN checkpoint | Code 0: HTTP 200 OK; publicly accessible and downloadable |
| 8 | Anonymous HTTP HEAD on `efficientnet_b0.onnx` blob & raw URLs | Check public exposure of BiSeNet checkpoint | Code 0: HTTP 200 OK; publicly accessible and downloadable |
| 9 | Anonymous HTTP HEAD on `face_reaging.onnx`, `.env`, `thirdeye_db.sql` | Check public exposure of restricted/sensitive files | Code 1 / HTTP 404 Not Found; properly excluded |
| 10 | Python streaming SHA-256 computation on all 8 model files | Recompute exact sizes and SHA-256 digests | Code 0: Exact sizes and checksums computed for all files |
| 11 | `os.stat('model/face_reaging/face_reaging.onnx')` | Check modification timestamp of FRAN checkpoint | Code 0: `st_mtime` is 2026-10-01 (unmodified since creation) |
| 12 | Code review of fallback logic in `face_reconstruction.py` & `face_variations.py` | Verify procedural fallback behavior when models missing | Code 0: Deterministic procedural fallbacks verified in code |

---

## 11. Confirmation of Zero Prohibited Modifications

In compliance with Phase 7.3 mandatory safety constraints, the following actions are explicitly confirmed:

1. **Zero Git Mutations:**
   - `git commit` was **NOT** executed.
   - `git push` was **NOT** executed.
   - `git add` (staging) was **NOT** executed.
   - `git reset` was **NOT** executed.
   - `git clean` was **NOT** executed.
   - `git restore` was **NOT** executed.
   - Git history was **NOT** rewritten, rebased, squashed, or filtered.
   - Branches and remotes were **NOT** created, renamed, or modified.
2. **Zero File Alterations:**
   - No source files, scripts, or model checkpoints were deleted, moved, renamed, or replaced.
   - All 8 model and mask files remain intact on disk in `C:\ThirdEye\model\`.
   - All uncommitted working-tree modifications from previous phases remain preserved.
3. **Zero Network Ingestion:**
   - No models, weights, datasets, or dependencies were downloaded.
4. **Zero Database Operations:**
   - The live MySQL database `thirdeye_db` was **NOT** accessed, connected to, queried, or modified.
5. **Zero Credential Disclosures:**
   - No private keys, database passwords, or personal case records were printed into reports or logs.

---

## Stop Condition Compliance
Phase 7.3 assessment and planning is complete. Execution is stopped for user review and approval before any remediation action is taken.
