# ThirdEye

**AI-Assisted Forensic Computer Vision System for Facial Analysis & Reconstruction**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11](https://img.shields.io/badge/Python-3.11-green.svg)](https://www.python.org/)
[![Framework: Flask](https://img.shields.io/badge/Framework-Flask_3.x-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Inference: CPU](https://img.shields.io/badge/Hardware-CPU_Optimized-orange.svg)]()

---

## Overview

**ThirdEye** is an AI-assisted forensic computer vision platform designed for digital composite sketch construction, generative facial reconstruction, biometric face identification, appearance variation modeling, and investigative poster production.

Built specifically for investigative workflows and academic demonstration, ThirdEye integrates deep learning models and deterministic image processing into a secure, auditable, two-role complaint investigation system. All vision pipelines run on standard consumer CPUs without requiring dedicated GPU hardware.

---

## Two Login Roles

ThirdEye strictly enforces a two-role access control model:

| Role | Target Actor | Responsibilities & Access |
|---|---|---|
| **Citizen (`user`)** | Public complainants and witnesses | Create, edit, and submit incident complaints; record incident location and details; provide suspect physical descriptions; upload initial evidence or construct composite sketches; submit requested information addenda; view status updates on own complaints. |
| **Police Administrator (`admin`)** | Forensic investigators and case officers | Review submitted complaints; approve or request further information; assign investigators; manage enrolled reference portraits; execute forensic operations (reconstruction, variations, biometric matching); generate and officially approve public missing/wanted posters; close completed investigations. |

Direct route access and URL manipulation are protected by ownership verification, CSRF enforcement, and role checks. Citizens cannot access investigator workspaces or unapproved public notices directly.

---

## The Sequential Complaint & Investigation Workflow

ThirdEye structures cases through an auditable, status-controlled lifecycle:

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
   ├─► Branch A or B Forensic Workspace
   ├─► Case-Bound Biometric Recognition (POST route only)
   ├─► Investigative Poster Draft Generation
   ├─► Admin Poster Review & Official Approval
   ▼
[Closed]
```

1. **Step-by-Step Complaint Creation Wizard:**
   - **Complainant Context:** Victim, witness, or legal representative context.
   - **Incident Details:** Date/time, classification, location mapping (Leaflet map pin or manual address), incident narrative (with optional browser speech transcription).
   - **Suspect Description:** Demographics, hair, eyes, clothing, accessories, marks, and facial reference selection.
   - **Evidence Submission:** Secure upload of photographic evidence, documents, audio, or canvas composite sketches.
2. **Review & Status Transitions:** Only authorized administrators can transition complaints between statuses. Every status change and administrative note is appended to an immutable case timeline.
3. **Information Requests & Citizen Addenda:** When administrators request additional details, citizens can submit supplementary statements and evidence without mutating original submissions.
4. **Case Closure:** Investigations can be officially closed by administrators with mandatory resolution summaries.

---

## Two Facial-Reference Branches

Investigations proceed along two distinct forensic reference pathways depending on evidence availability:

### Branch A — No Photograph Available (Composite Sketch Route)
- **Workflow:** Complainants or composite artists assemble a facial sketch using the interactive HTML5 canvas constructor (176 facial components: hair, eyes, nose, mouth, face shape, accessories).
- **Generative Reconstruction:** A TorchScript ResNet-6 CycleGAN neural network (`model/sketch_to_face/cyclegan_model.pt`) reconstructs a candidate photographic rendering with customizable skin tone adaptation.
- **Forensic Lineage:** The generated output is stored as a derived artifact linked to the parent sketch evidence ID with SHA-256 integrity digest and generation metadata.
- **Ethical Safeguard & Biometric Block:** The reconstructed face displays a mandatory project disclaimer watermark (*“AI-generated reconstruction — illustrative only; not a verified identity.”*). Biometric face recognition is **strictly prohibited** on synthetic reconstructions.

### Branch B — Authentic, Unmasked Photograph (High-Quality Photographic Evidence)
- **Workflow:** Complainant uploads an authentic, unmasked photograph or surveillance capture.
- **Evidence Immutability:** The original photograph remains byte-for-byte immutable in private case storage (`instance/case_storage/`) with verified SHA-256 digest. Generative reconstruction is skipped by default.
- **Appearance Variations:** Investigators can model probable longitudinal aging (FRAN ONNX model or procedural fallback), alternative hairstyles, and facial hair variations anchored to 68 anthropometric facial landmarks (`static/variation_assets_photo/` with fallback to `static/variation_assets/`).
- **Biometric Matching:** Case-bound face recognition extracts a 128-dimensional biometric embedding via `dlib` and compares against enrolled reference records (`persons` table). Matching executes exclusively via protected POST routes and logs search activity to the case timeline.

---

## Controlled Poster Generation & Gated Public Notices

Investigative posters (DIN A4 missing person notices and wanted flyers) are generated using ReportLab across 5 layout templates:
1. Posters generated inside a case remain in private case storage marked as **unapproved drafts** (`access_level='internal'`).
2. Public downloads or unauthorized access attempts to unapproved posters are rejected with `HTTP 403 Forbidden`.
3. Only an authenticated Administrator can inspect the poster draft and grant explicit publication approval (`access_level='public_notice'`).

---

## System Requirements & Technology Stack

### Hardware & OS Requirements
- **Operating System:** Windows 10 / 11 (64-bit; also compatible with Linux / macOS).
- **CPU:** Standard Intel Core i3/i5+ or AMD Ryzen multi-core processor.
- **RAM:** 8 GB system RAM recommended (minimum 4 GB).
- **GPU:** **No GPU or NVIDIA CUDA required.** All neural models run on CPU.
- **Storage:** ~220 MB for the clean distributable codebase + active AI models (~1.5 GB including Anaconda environment).

### Verified Software & Package Stack
- **Python Version:** Python **3.11.x** (64-bit)
- **Database:** MySQL **8.0+** or MariaDB **10.3+** (`InnoDB`, `utf8mb4`); in-memory SQLite for isolated automated tests
- **Verified Packages** (see [`requirements.txt`](requirements.txt)):
  - `Flask>=3.0.0,<4.0.0` (verified `3.1.3`), `Werkzeug>=3.0.0,<4.0.0` (verified `3.1.8`)
  - `Flask-SQLAlchemy>=3.1.0,<4.0.0` (verified `3.1.1`), `SQLAlchemy>=2.0.0,<3.0.0` (verified `2.0.52`)
  - `Flask-Bcrypt>=1.0.1,<2.0.0` (verified `1.0.1`), `Flask-WTF==1.3.0`, `WTForms>=3.2.0` (verified `3.2.2`)
  - `mysql-connector-python>=8.0.0` (verified `26.7.0`)
  - `opencv-python==4.11.0.86`, `numpy>=1.24.0,<2.0.0` (verified `1.26.4`), `Pillow>=10.0.0` (verified `11.1.0`)
  - `dlib>=19.24.0` (verified `19.24.0`), `face_recognition>=1.3.0`, `face_recognition_models>=0.3.0`
  - `torch>=2.0.0` (verified `2.14.0+cpu`), `onnxruntime>=1.16.0` (verified `1.30.0`), `scipy>=1.11.0` (verified `1.15.2`)
  - `reportlab>=4.0.0` (verified `5.0.1`)
  - `setuptools>=68.0.0,<82` (keeps `pkg_resources` available for `face_recognition_models`)

---

## Step-by-Step Setup & Windows Transfer Guide (From Scratch)

Follow these exact steps when setting up ThirdEye on a fresh Windows 10/11 laptop (via folder copy, ZIP archive, or repository clone).

### Step 1: Copy or Extract the Project Folder
Place the ThirdEye folder in a clean, non-synced directory (for example, `C:\ThirdEye\` — avoid OneDrive-synced folders if running heavy file I/O) and open **Anaconda Prompt** (or PowerShell with Conda initialized) inside that folder:
```cmd
cd /d C:\ThirdEye
```

### Step 2: Create a Clean Python 3.11 Environment
Anaconda or Miniconda is strongly recommended on Windows so compiled C++ libraries (`dlib`) install cleanly without requiring Visual Studio Build Tools.

```cmd
conda create -n ThirdEye311 python=3.11 -y
conda activate ThirdEye311
```

### Step 3: Install `dlib`, CPU PyTorch, and Requirements
Run these three commands in order inside your activated `ThirdEye311` environment:

```cmd
:: 1. Install precompiled dlib (avoids needing CMake + Visual Studio C++ Compiler on Windows)
conda install -c conda-forge dlib -y

:: 2. Install CPU-only PyTorch (downloads ~200 MB instead of ~2.5 GB CUDA wheel)
pip install torch --index-url https://download.pytorch.org/whl/cpu

:: 3. Install remaining ThirdEye dependencies
pip install -r requirements.txt
```

> *(If not using Conda, install CMake and Visual Studio C++ Desktop Development Build Tools before running `pip install -r requirements.txt`, or install a matching Python 3.11 Windows `dlib` wheel first.)*

Verify that all installed packages are healthy:
```cmd
python -m pip check
python -c "import flask, cv2, dlib, face_recognition, torch, onnxruntime, reportlab, mysql.connector; print('Environment OK')"
```
Expected output:
- `No broken requirements found.`
- `Environment OK`

---

## Database Setup & SQL Import Procedure

ThirdEye includes a clean schema script: [`thirdeye_db.example.sql`](thirdeye_db.example.sql). It uses `CREATE DATABASE IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` for all five tables (`users`, `persons`, `complaints`, `complaint_evidence`, `complaint_timeline`) and inserts one neutral synthetic record (`Demo Subject` linked to `static/person_db/test_person.jpg`).

### Step 1: Start MySQL Server on the New Laptop
Ensure **MySQL Server 8.0+** (or MariaDB / XAMPP MySQL) is installed and running on port `3306`.

### Step 2: Import [`thirdeye_db.example.sql`](thirdeye_db.example.sql)

#### Option A — Command Prompt (`cmd`)
In Windows **Command Prompt** (note: use `cmd`, not PowerShell `<` redirection):
```cmd
mysql -u root -p < thirdeye_db.example.sql
```
*(In PowerShell, run: `Get-Content thirdeye_db.example.sql | mysql -u root -p` or `cmd /c "mysql -u root -p < thirdeye_db.example.sql"`.)*

#### Option B — MySQL Workbench (GUI)
1. Open **MySQL Workbench** and connect to your local MySQL instance.
2. Click **File → Open SQL Script...** and select `thirdeye_db.example.sql`.
3. Click the **Execute (Lightning Bolt)** icon and refresh **Schemas** to verify `thirdeye_db` and its 5 tables exist.

#### Option C — phpMyAdmin (XAMPP/WAMP)
1. Open `http://localhost/phpmyadmin`.
2. Open the **Import** tab, choose `thirdeye_db.example.sql`, and click **Go**.

---

## Environment Configuration (`.env`)

Never copy an old `.env` containing another computer's passwords or secret keys. Instead, create a fresh `.env` from [`.env.example`](.env.example):

```cmd
copy .env.example .env
```

Edit `.env` with Notepad or VS Code:
```ini
FLASK_ENV=development
THIRDEYE_COOKIE_SECURE=false

# Generate a unique random key with:
#   python -c "import secrets; print(secrets.token_hex(32))"
THIRDEYE_SECRET_KEY=paste_your_generated_64_char_hex_secret_here

# Local MySQL connection details
THIRDEYE_DB_HOST=127.0.0.1
THIRDEYE_DB_PORT=3306
THIRDEYE_DB_USER=root
THIRDEYE_DB_PASSWORD=your_mysql_password
THIRDEYE_DB_NAME=thirdeye_db
```

> **Note:** `app.py` parses `.env` directly via `_load_env_file()`, so `python-dotenv` is not required.
>
> **Security Modes:**
> - **Development (`FLASK_ENV=development`):** Allows local HTTP testing (`THIRDEYE_COOKIE_SECURE=false`). If `THIRDEYE_SECRET_KEY` is omitted, a temporary random key is generated at startup with a warning.
> - **Production (`FLASK_ENV=production`):** Requires a non-empty `THIRDEYE_SECRET_KEY` (fails closed on startup otherwise) and enforces `SESSION_COOKIE_SECURE=True` (HTTPS required for session cookies).

---

## Provision Accounts & Run ThirdEye

### 1. Create the Initial Administrator Account
Before logging in as an investigator/administrator, provision your admin credentials:
```cmd
python create_admin.py admin YourStrongAdminPassword123!
```
You can also provision a sample citizen user from CLI (or register directly in the browser at `/register`):
```cmd
python create_user.py citizen1 CitizenPassword123! user
```

### 2. Launch the Application
Use the convenient Windows launchers (which detect `ThirdEye311` automatically) or run Python directly:
- **Command Prompt:** `run.bat`
- **PowerShell:** `.\run.ps1`
- **Direct Python (inside activated `ThirdEye311`):** `python app.py`

Open your browser and go to:
```
http://127.0.0.1:5000
```

---

## Model Assets & Storage

ThirdEye runs entirely offline for AI inference once installed:

| Model | File Path | File Size | Execution Provider | Purpose & Status |
|---|---|---|---|---|
| **CycleGAN Generator** | `model/sketch_to_face/cyclegan_model.pt` | 30.04 MB | PyTorch CPU (TorchScript) | Active — Branch A sketch-to-face reconstruction (with procedural fallback if absent). |
| **BiSeNet Face Parser** | `model/face_parsing/efficientnet_b0.onnx` | 26.28 MB | ONNX Runtime (`CPUExecutionProvider`) | Active — Semantic hair/skin parsing for appearance variations. |
| **FRAN Re-Aging Network** | `model/face_reaging/face_reaging.onnx` (+ masks) | 118.48 MB | ONNX Runtime (`CPUExecutionProvider`) | Active — Longitudinal age adjustment (non-commercial research license; procedural aging fallback engages automatically if absent). |
| **dlib Landmarks & ResNet-34** | Provided by `face_recognition_models` package | ~100 MB | `dlib` CPU | Active — 68 facial landmarks & 128-D biometric face encodings. |

> *Note: An experimental unreferenced LaMa inpainting prototype (`services/local_illustration.py` + `model/face_inpainting/lama_fp32.onnx`, 198.41 MB) is unused by active routes and excluded from the lean distributable package.*

---

## Isolated Automated Regression Testing

ThirdEye ships with a fail-closed test runner ([`scripts/run_isolated_tests.py`](scripts/run_isolated_tests.py)) that guarantees **zero interaction with your MySQL database**:
- Forces in-memory SQLite (`sqlite:///:memory:`) before importing application modules.
- Blocks raw `mysql.connector.connect()` calls at the library level.
- Disables periodic disk cleanup and uses temporary test storage directories.

### Quick Verification Commands
```cmd
:: Self-check isolated SQLite setup & fail-closed guard
python scripts/run_isolated_tests.py --self-check
python scripts/run_isolated_tests.py --fail-closed-test

:: Run the core active workflow & security test suites
python scripts/run_isolated_tests.py --suite test_phase2_complaint_models.py
python scripts/run_isolated_tests.py --suite test_phase3_complaints.py
python scripts/run_isolated_tests.py --suite test_phase4_workflow.py
python scripts/run_isolated_tests.py --suite test_phase5_forensic_artifacts.py
python scripts/run_isolated_tests.py --suite test_phase5_1_biometric_case_binding.py
python scripts/run_isolated_tests.py --suite test_phase6_security_reliability.py
python scripts/run_isolated_tests.py --suite test_phase6_1_csrf_security.py
python scripts/run_isolated_tests.py --suite test_phase6_2_config_security.py
```

---

## Troubleshooting & Limitations

1. **Offline / Air-Gapped Maps:** The complaint location picker loads Leaflet & OpenStreetMap tiles from the web. If offline, type location addresses and coordinates directly into the form fields.
2. **Browser Voice Dictation:** Voice-to-text narrative dictation requires Chromium-based browsers (Chrome or Edge) and microphone permission; manual typing always works.
3. **CPU Inference Times:** Expect ~3–6 seconds for CycleGAN reconstruction or BiSeNet + FRAN appearance variations on typical laptop CPUs. Avoid launching concurrent heavy jobs on 4 GB RAM systems.
4. **Forensic & Biometric Notice:** Synthetic reconstructions and speculative variations are **illustrative hypotheses only** and never admissible as verified identity matches. Biometric matching requires reasonably frontal photographs ($\pm 25^\circ$ yaw) and is strictly blocked on sketches, reconstructions, masked photos, and variations.

---

## License & Attribution

- **ThirdEye Source Code:** [MIT License](LICENSE)
- **BiSeNet Parser Architecture:** MIT License ([Mrkomiljon/face-parsing](https://github.com/Mrkomiljon/face-parsing))
- **FRAN Re-Aging Architecture:** Disney Research (Non-commercial research use; ONNX export from [Glat0s/face_reaging-onnx](https://github.com/Glat0s/face_reaging-onnx))
- **dlib / face_recognition:** Boost Software License 1.0 / MIT License
