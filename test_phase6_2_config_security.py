"""
test_phase6_2_config_security.py — ThirdEye Phase 6.2 Test Suite
================================================================
Focused verification of Secret-Key Hardening, Configuration Isolation,
CSRF Protection Persistence, and the Information-Request Status Lifecycle.

Covers:
 1. Production startup fails safely when THIRDEYE_SECRET_KEY is missing.
 2. Production startup fails safely when THIRDEYE_SECRET_KEY is empty.
 3. Production configuration uses the explicitly supplied environment key.
 4. Development/testing without a key uses a random temporary value (distinct per run).
 5. CSRF protection remains enabled with a correctly configured key.
 6. Valid CSRF token permits authorized operations.
 7. Missing and invalid CSRF tokens reject protected requests.
 8. Startup errors and logs do not reveal secret content.
 9. Complete regression test for 'information_requested' status and citizen addendum lifecycle.
 10. Fail-closed SQLite in-memory isolation with zero live MySQL access.
"""

import os
import sys
import subprocess
import unittest
import io
import shutil
import tempfile
import secrets
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer
from werkzeug.datastructures import FileStorage

# Windows Anaconda DLL registration
_PORTABLE_DLL_DIRS = []
if sys.platform == 'win32':
    candidate_dll_dirs = [
        os.path.join(sys.prefix, "Library", "bin"),
        os.path.join(sys.prefix, "DLLs"),
        os.path.join(sys.base_prefix, "Library", "bin"),
        os.path.join(sys.base_prefix, "DLLs"),
    ]
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidate_dll_dirs.insert(0, os.path.join(conda_prefix, "Library", "bin"))
    for d in candidate_dll_dirs:
        if os.path.isdir(d) and d not in _PORTABLE_DLL_DIRS:
            _PORTABLE_DLL_DIRS.append(d)
            try:
                os.add_dll_directory(d)
            except (AttributeError, OSError):
                pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_SUBPROCESS_DLL_PRELUDE = (
    "import os, sys; "
    "[os.add_dll_directory(d) for d in ("
    "os.path.join(sys.prefix, 'Library', 'bin'), "
    "os.path.join(sys.base_prefix, 'Library', 'bin')"
    ") if os.path.isdir(d)]; "
)


def _subprocess_env_with_dlls(base_env):
    if _PORTABLE_DLL_DIRS:
        prefix = os.pathsep.join(_PORTABLE_DLL_DIRS)
        existing = base_env.get('PATH', '')
        base_env['PATH'] = f"{prefix}{os.pathsep}{existing}" if existing else prefix
    return base_env

# Enforce fail-closed SQLite in-memory isolation before importing app
os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
os.environ["TESTING"] = "True"
os.environ["FLASK_ENV"] = "testing"

try:
    import mysql.connector
    def _blocked_mysql(*args, **kwargs):
        raise RuntimeError("FAIL-CLOSED: MySQL access blocked in isolated verification!")
    mysql.connector.connect = _blocked_mysql
except ImportError:
    pass

from app import app, db
from models import (
    User,
    Complaint,
    ComplaintEvidence,
    ComplaintTimeline,
    ALLOWED_COMPLAINT_STATUSES
)
from services.complaint_service import (
    create_draft_complaint,
    update_draft_complaint,
    submit_complaint,
    attach_evidence_file
)
from services.workflow_service import (
    transition_case_status,
    submit_case_addendum
)

PYTHON_EXE = sys.executable


class Phase62ConfigSecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = True
        app.config['WTF_CSRF_CHECK_DEFAULT'] = True
        app.config['SECRET_KEY'] = 'phase6_2_test_explicit_key_32bytes!'
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()

        # Seed test citizen and admin
        self.citizen = User(
            username="citizen_p62",
            password="CitizenPassword123!",
            role="user",
            full_name="Citizen P62"
        )
        self.admin = User(
            username="admin_p62",
            password="AdminPassword123!",
            role="admin",
            full_name="Admin P62"
        )
        db.session.add_all([self.citizen, self.admin])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _get_csrf_token(self, client=None):
        target = client or self.client
        with target.session_transaction() as sess:
            raw_token = sess.get('csrf_token')
            if not raw_token:
                raw_token = secrets.token_hex(32)
                sess['csrf_token'] = raw_token
        serializer = URLSafeTimedSerializer(app.secret_key, salt='wtf-csrf-token')
        return serializer.dumps(raw_token)

    def _login(self, username, password, client=None):
        target = client or self.client
        token = self._get_csrf_token(target)
        return target.post('/login', data={
            'username': username,
            'password': password,
            'csrf_token': token
        }, follow_redirects=False)

    # =========================================================================
    # Gate 1: Production startup fails safely when THIRDEYE_SECRET_KEY is missing
    # =========================================================================
    def test_01_production_startup_fails_when_secret_key_missing(self):
        """Gate 1: In production mode, missing THIRDEYE_SECRET_KEY fails startup with a safe error."""
        code = _SUBPROCESS_DLL_PRELUDE + "from app import app"
        env = os.environ.copy()
        env['FLASK_ENV'] = 'production'
        env['THIRDEYE_IGNORE_DOTENV'] = '1'
        env.pop('THIRDEYE_SECRET_KEY', None)
        env['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        _subprocess_env_with_dlls(env)

        proc = subprocess.run(
            [PYTHON_EXE, "-c", code],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            env=env
        )
        self.assertNotEqual(proc.returncode, 0, "Startup must fail in production when key is missing")
        self.assertIn("THIRDEYE_SECRET_KEY environment variable is required", proc.stderr)
        self.assertIn("production mode", proc.stderr)

    # =========================================================================
    # Gate 2: Production startup fails safely when THIRDEYE_SECRET_KEY is empty
    # =========================================================================
    def test_02_production_startup_fails_when_secret_key_empty(self):
        """Gate 2: In production mode, an empty or whitespace THIRDEYE_SECRET_KEY fails startup."""
        for empty_val in ["", "   "]:
            code = _SUBPROCESS_DLL_PRELUDE + "from app import app"
            env = os.environ.copy()
            env['FLASK_ENV'] = 'production'
            env['THIRDEYE_IGNORE_DOTENV'] = '1'
            env['THIRDEYE_SECRET_KEY'] = empty_val
            env['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
            _subprocess_env_with_dlls(env)

            proc = subprocess.run(
                [PYTHON_EXE, "-c", code],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                env=env
            )
            self.assertNotEqual(proc.returncode, 0, f"Startup must fail when key is {repr(empty_val)}")
            self.assertIn("THIRDEYE_SECRET_KEY environment variable is required", proc.stderr)

    # =========================================================================
    # Gate 3: Production configuration uses the supplied environment key
    # =========================================================================
    def test_03_production_configuration_uses_supplied_environment_key(self):
        """Gate 3: In production mode, the explicitly supplied environment key is used."""
        test_key = "production_explicit_secure_key_abcdef123456"
        code = _SUBPROCESS_DLL_PRELUDE + "from app import app; print('RESOLVED_KEY:' + app.config['SECRET_KEY'])"
        env = os.environ.copy()
        env['FLASK_ENV'] = 'production'
        env['THIRDEYE_IGNORE_DOTENV'] = '1'
        env['THIRDEYE_SECRET_KEY'] = test_key
        env['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        _subprocess_env_with_dlls(env)

        proc = subprocess.run(
            [PYTHON_EXE, "-c", code],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            env=env
        )
        self.assertEqual(proc.returncode, 0, f"Startup failed with valid key: {proc.stderr}")
        output_lines = [l.strip() for l in proc.stdout.splitlines() if l.startswith('RESOLVED_KEY:')]
        self.assertTrue(len(output_lines) > 0, f"RESOLVED_KEY not found in output: {proc.stdout}")
        self.assertEqual(output_lines[0], 'RESOLVED_KEY:' + test_key)

    # =========================================================================
    # Gate 4: Development without a key uses a random temporary value (distinct per run)
    # =========================================================================
    def test_04_development_without_key_uses_random_temporary_value(self):
        """Gate 4: In development mode without a key, a fresh random key is generated each run (not a fixed fallback)."""
        code = _SUBPROCESS_DLL_PRELUDE + "from app import app; print('RANDOM_KEY:' + app.config['SECRET_KEY'])"
        env = os.environ.copy()
        env['FLASK_ENV'] = 'development'
        env['THIRDEYE_IGNORE_DOTENV'] = '1'
        env.pop('THIRDEYE_SECRET_KEY', None)
        env['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        _subprocess_env_with_dlls(env)

        # Run 1
        proc1 = subprocess.run([PYTHON_EXE, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, env=env)
        self.assertEqual(proc1.returncode, 0, f"Run 1 failed: {proc1.stderr}")
        lines1 = [l.strip() for l in proc1.stdout.splitlines() if l.startswith('RANDOM_KEY:')]
        self.assertTrue(len(lines1) > 0)
        key1 = lines1[0].split('RANDOM_KEY:')[1]

        # Run 2
        proc2 = subprocess.run([PYTHON_EXE, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, env=env)
        self.assertEqual(proc2.returncode, 0, f"Run 2 failed: {proc2.stderr}")
        lines2 = [l.strip() for l in proc2.stdout.splitlines() if l.startswith('RANDOM_KEY:')]
        self.assertTrue(len(lines2) > 0)
        key2 = lines2[0].split('RANDOM_KEY:')[1]

        # Both keys must have sufficient length and entropy
        self.assertGreaterEqual(len(key1), 32)
        self.assertGreaterEqual(len(key2), 32)

        # The two runs must generate DIFFERENT keys (proves dynamic randomness, not a hardcoded fallback)
        self.assertNotEqual(key1, key2, "Development without key must generate distinct random keys, not a fixed fallback!")

        # A RuntimeWarning must be emitted
        self.assertIn("SECURITY WARNING: THIRDEYE_SECRET_KEY is not configured", proc1.stderr)

    # =========================================================================
    # Gate 5: CSRF protection remains enabled with correctly configured key
    # =========================================================================
    def test_05_csrf_protection_enabled_with_configured_key(self):
        """Gate 5: CSRF protection is active globally; unprotected POST requests are rejected with HTTP 400."""
        resp = self.client.post('/login', data={'username': 'citizen_p62', 'password': 'CitizenPassword123!'})
        self.assertEqual(resp.status_code, 400, "Unprotected POST must be rejected with HTTP 400")

    # =========================================================================
    # Gate 6: Valid CSRF token permits authorized operations
    # =========================================================================
    def test_06_valid_csrf_token_permits_authorized_operations(self):
        """Gate 6: Supplying a valid CSRF token permits authorized login and complaint actions."""
        resp = self._login('citizen_p62', 'CitizenPassword123!')
        self.assertEqual(resp.status_code, 302)

        token = self._get_csrf_token()
        resp_comp = self.client.post('/complaints/new', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(resp_comp.status_code, 302)
        self.assertIn('/edit', resp_comp.headers['Location'])

    # =========================================================================
    # Gate 7: Missing and invalid CSRF tokens reject protected requests
    # =========================================================================
    def test_07_missing_and_invalid_csrf_tokens_reject_protected_requests(self):
        """Gate 7: Invalid or missing CSRF tokens consistently return HTTP 400."""
        # Bogus token
        resp1 = self.client.post('/login', data={
            'username': 'citizen_p62',
            'password': 'CitizenPassword123!',
            'csrf_token': 'malformed_token_12345'
        })
        self.assertEqual(resp1.status_code, 400)

        # Missing token
        resp2 = self.client.post('/complaints/new')
        self.assertEqual(resp2.status_code, 400)

    # =========================================================================
    # Gate 8: Startup errors and logs do not reveal secret content
    # =========================================================================
    def test_08_startup_errors_and_logs_do_not_reveal_secrets(self):
        """Gate 8: Startup error messages and warnings never expose secret keys."""
        code = _SUBPROCESS_DLL_PRELUDE + "from app import app"
        env = os.environ.copy()
        env['FLASK_ENV'] = 'production'
        env['THIRDEYE_IGNORE_DOTENV'] = '1'
        env.pop('THIRDEYE_SECRET_KEY', None)
        env['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        _subprocess_env_with_dlls(env)

        proc = subprocess.run([PYTHON_EXE, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, env=env)
        # Ensure stderr does not mention any fake or real secret
        self.assertNotIn("thirdeye_production_secret_key_fixed_998877", proc.stderr)
        self.assertNotIn("isolated_test_secret_key", proc.stderr)

    # =========================================================================
    # =========================================================================
    # Gate 9: Regression test for 'information_requested' status & citizen addendum lifecycle
    # =========================================================================
    def test_09_information_requested_status_and_addendum_lifecycle(self):
        """Gate 9: Complete lifecycle test verifying 'information_requested' naming, persistence, and addendum return."""
        # Verify established status naming in models
        self.assertIn('information_requested', ALLOWED_COMPLAINT_STATUSES)
        self.assertNotIn('info_req', ALLOWED_COMPLAINT_STATUSES, "'info_req' must not exist in models.ALLOWED_COMPLAINT_STATUSES")
        self.assertNotIn('under_investigation', ALLOWED_COMPLAINT_STATUSES, "'under_investigation' must not exist in models.ALLOWED_COMPLAINT_STATUSES")
        self.assertIn('under_review', ALLOWED_COMPLAINT_STATUSES)
        self.assertIn('investigation_in_progress', ALLOWED_COMPLAINT_STATUSES)

        # 1. Citizen creates draft & attaches initial evidence
        draft = create_draft_complaint(self.citizen.id)
        orig_narrative = 'Blue hybrid bicycle locked at bike rack was missing in the afternoon.'
        update_draft_complaint(draft.id, self.citizen.id, {
            'title': 'Stolen Bicycle from Courtyard',
            'category': 'Theft / Burglary',
            'incident_at': '2026-10-10T14:00',
            'location_address': 'Building 8 Courtyard, Sector 3',
            'narrative': orig_narrative
        })

        initial_png = b"\x89PNG\r\n\x1a\n" + b"\x11" * 32
        init_fs = FileStorage(stream=io.BytesIO(initial_png), filename="bike_parking_spot.png", content_type="image/png")
        attach_evidence_file(draft.id, self.citizen.id, init_fs)

        # Citizen submits complaint -> status becomes 'submitted'
        case = submit_complaint(draft.id, self.citizen.id)
        self.assertEqual(case.status, 'submitted')
        self.assertEqual(case.evidence.count(), 1)

        # Verify DB persisted state
        persisted_case = Complaint.query.filter_by(id=case.id).first()
        self.assertIsNotNone(persisted_case)
        self.assertEqual(persisted_case.status, 'submitted')
        self.assertEqual(persisted_case.narrative, orig_narrative)

        # 2. Admin starts review -> 'under_review'
        transition_case_status(case.id, self.admin.id, 'under_review')
        persisted_case = Complaint.query.filter_by(id=case.id).first()
        self.assertEqual(persisted_case.status, 'under_review')

        # 3. Admin requests info -> 'information_requested'
        request_msg = "Please upload purchase invoice or frame serial number photograph."
        transition_case_status(case.id, self.admin.id, 'information_requested', message=request_msg)
        persisted_case = Complaint.query.filter_by(id=case.id).first()
        self.assertEqual(persisted_case.status, 'information_requested', "Status must strictly be 'information_requested'")

        # Verify timeline recorded with exact event_type and actor
        tl_request = persisted_case.timeline.filter_by(event_type='information_requested').first()
        self.assertIsNotNone(tl_request)
        self.assertEqual(tl_request.message, request_msg)
        self.assertEqual(tl_request.new_status, 'information_requested')
        self.assertEqual(tl_request.actor_user_id, self.admin.id)

        # 4. Citizen responds with addendum via submit_case_addendum
        addendum_notes = "Serial number: BIK-99210; attached invoice photo."
        valid_png = b"\x89PNG\r\n\x1a\n" + b"\x22" * 32
        supp_fs = FileStorage(stream=io.BytesIO(valid_png), filename="bike_invoice.png", content_type="image/png")
        
        updated_case = submit_case_addendum(
            complaint_id=case.id,
            user_id=self.citizen.id,
            addendum_text=addendum_notes,
            supplementary_files=[supp_fs]
        )

        # Query fresh from database session to verify real persistence
        db.session.expire_all()
        fresh_persisted = Complaint.query.filter_by(id=case.id).first()
        self.assertIsNotNone(fresh_persisted)

        # 7. The case transitions to the intended valid next status ('under_review')
        self.assertEqual(fresh_persisted.status, 'under_review', "Addendum submission must transition status back to 'under_review'")
        self.assertIn(fresh_persisted.status, ALLOWED_COMPLAINT_STATUSES)

        # 5. Original narrative and evidence remain 100% unchanged
        self.assertEqual(fresh_persisted.narrative, orig_narrative, "Original complaint narrative was mutated!")
        initial_ev = fresh_persisted.evidence.filter_by(original_filename='bike_parking_spot.png').first()
        self.assertIsNotNone(initial_ev, "Initial evidence record was lost!")

        # 6. Supplementary information is appended
        self.assertEqual(fresh_persisted.evidence.count(), 2, "Evidence count must reflect additive supplementary file")
        supp_ev = fresh_persisted.evidence.filter_by(original_filename='bike_invoice.png').first()
        self.assertIsNotNone(supp_ev, "Supplementary evidence record missing!")
        self.assertEqual(supp_ev.source_kind, 'uploaded')

        # 8. Timeline entries accurately record each event
        tl_events = [t.event_type for t in fresh_persisted.timeline.order_by(ComplaintTimeline.created_at.asc()).all()]
        self.assertIn('complaint_submitted', tl_events)
        self.assertIn('review_started', tl_events)
        self.assertIn('information_requested', tl_events)
        self.assertIn('information_response', tl_events)

        tl_addendum = fresh_persisted.timeline.filter_by(event_type='information_response').first()
        self.assertIsNotNone(tl_addendum)
        self.assertIn(addendum_notes, tl_addendum.message)
        self.assertEqual(tl_addendum.actor_user_id, self.citizen.id)

    # =========================================================================
    # Gate 10: Fail-closed SQLite in-memory isolation with zero live MySQL writes
    # =========================================================================
    def test_10_zero_live_mysql_writes(self):
        """Gate 10: Enforces fail-closed SQLite in-memory dialect with live MySQL blocked."""
        engine_url = str(db.engine.url)
        self.assertTrue(engine_url.startswith("sqlite:///:memory:") or engine_url.startswith("sqlite://"))
        self.assertEqual(db.engine.dialect.name, "sqlite")


if __name__ == '__main__':
    unittest.main()
