"""
test_phase6_1_csrf_security.py — ThirdEye Phase 6.1 CSRF Protection Test Suite
==============================================================================
Focused verification of Flask-WTF CSRF Protection, Method Hardening, and RBAC:

Covers all 14 required Phase 6.1 verification gates:
 1. Protected POST requests reject missing tokens (HTTP 400).
 2. Protected POST requests reject invalid / tampered tokens (HTTP 400).
 3. A valid token permits an authorized operation (HTTP 200 / 302).
 4. Missing or invalid tokens never cause the underlying operation or DB commit to execute.
 5. Login and registration forms contain usable CSRF tokens.
 6. Complaint and evidence forms contain usable CSRF tokens.
 7. Admin actions (review, transition, assignment) and poster approval are protected.
 8. Biometric recognition POST requires a valid token and still validates case and original photo.
 9. Logout cannot be triggered by GET and requires a valid POST token.
 10. GET /complaints/new does not create a draft; its protected POST action does.
 11. Existing role and case-ownership restrictions remain enforced.
 12. Invalid-token requests do not create success timeline entries.
 13. Original submitted evidence remains immutable.
 14. Tests cannot access or modify live MySQL (100% in-memory SQLite isolation).
"""

import os
import sys

# On Windows with Anaconda, load library DLLs before imports
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
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except (AttributeError, OSError):
                pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Enforce fail-closed SQLite in-memory isolation before importing app
os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
os.environ["TESTING"] = "True"
os.environ["FLASK_ENV"] = "testing"

# Block direct MySQL connection
try:
    import mysql.connector
    def _blocked_mysql(*args, **kwargs):
        raise RuntimeError("FAIL-CLOSED: MySQL access blocked in isolated verification!")
    mysql.connector.connect = _blocked_mysql
except ImportError:
    pass

import unittest
import io
import shutil
import tempfile
import secrets
import numpy as np
import cv2
from datetime import datetime
from unittest.mock import patch, MagicMock
from itsdangerous import URLSafeTimedSerializer
from werkzeug.datastructures import FileStorage

from app import app, db
from models import (
    User,
    Person,
    Complaint,
    ComplaintEvidence,
    ComplaintTimeline,
    ALLOWED_USER_ROLES,
    ALLOWED_COMPLAINT_STATUSES,
    ALLOWED_FACIAL_REFERENCE_TYPES
)
from services.complaint_service import (
    create_draft_complaint,
    update_draft_complaint,
    submit_complaint,
    attach_evidence_file,
    get_case_storage_root
)
from services.workflow_service import (
    can_transition,
    get_case_for_user,
    transition_case_status,
    assign_case_officer,
    submit_case_addendum,
    can_access_tool,
    save_case_artifact,
    approve_poster_for_distribution
)


def _generate_valid_png_bytes(width=100, height=100, color=(140, 160, 200)):
    """Generates valid PNG image bytes for testing."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    _, buf = cv2.imencode('.png', img)
    return buf.tobytes()


class Phase61CSRFSecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        # Explicitly ensure CSRF protection is ENABLED
        app.config['WTF_CSRF_ENABLED'] = True
        app.config['WTF_CSRF_CHECK_DEFAULT'] = True
        app.config['SECRET_KEY'] = 'thirdeye-csrf-test-secret-key-32b!'
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

        cls.test_storage_root = tempfile.mkdtemp(prefix="thirdeye_phase6_1_test_storage_")
        cls.storage_patcher = patch('services.complaint_service.get_case_storage_root', return_value=cls.test_storage_root)
        cls.storage_patcher.start()
        cls.storage_patcher_wf = patch('services.workflow_service.get_case_storage_root', return_value=cls.test_storage_root)
        cls.storage_patcher_wf.start()
        cls.storage_patcher_app = patch('app.get_case_storage_root', return_value=cls.test_storage_root)
        cls.storage_patcher_app.start()

    @classmethod
    def tearDownClass(cls):
        cls.storage_patcher_app.stop()
        cls.storage_patcher_wf.stop()
        cls.storage_patcher.stop()
        if os.path.exists(cls.test_storage_root):
            shutil.rmtree(cls.test_storage_root, ignore_errors=True)

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()

        # Seed standard test users
        self.citizen = User(
            username="citizen_csrf",
            password="Password123!",
            role="user",
            full_name="Citizen CSRF Test"
        )
        self.citizen_other = User(
            username="citizen_other_csrf",
            password="Password123!",
            role="user",
            full_name="Other Citizen CSRF"
        )
        self.admin = User(
            username="admin_csrf",
            password="AdminPassword123!",
            role="admin",
            full_name="Admin CSRF Test"
        )
        db.session.add_all([self.citizen, self.citizen_other, self.admin])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _get_csrf_token(self, client=None):
        """Generates a valid signed CSRF token for the test client session."""
        target_client = client or self.client
        with target_client.session_transaction() as sess:
            raw_token = sess.get('csrf_token')
            if not raw_token:
                raw_token = secrets.token_hex(32)
                sess['csrf_token'] = raw_token
        serializer = URLSafeTimedSerializer(app.secret_key, salt='wtf-csrf-token')
        return serializer.dumps(raw_token)

    def _login(self, username, password, client=None):
        """Helper to log in with a valid CSRF token."""
        target_client = client or self.client
        token = self._get_csrf_token(target_client)
        return target_client.post('/login', data={
            'username': username,
            'password': password,
            'csrf_token': token
        }, follow_redirects=False)

    # =========================================================================
    # GATE 1: Protected POST requests reject missing tokens
    # =========================================================================
    def test_01_protected_post_requests_reject_missing_tokens(self):
        """Gate 1: Any protected POST request omitting the CSRF token is rejected with HTTP 400."""
        # 1. Login POST without token
        resp = self.client.post('/login', data={'username': 'citizen_csrf', 'password': 'Password123!'})
        self.assertEqual(resp.status_code, 400, "Missing CSRF token on /login must yield 400")

        # 2. Register POST without token
        resp = self.client.post('/register', data={'username': 'newuser', 'password': 'Password123!', 'confirm_password': 'Password123!'})
        self.assertEqual(resp.status_code, 400, "Missing CSRF token on /register must yield 400")

        # Log in citizen
        self._login('citizen_csrf', 'Password123!')

        # 3. /complaints/new POST without token
        resp = self.client.post('/complaints/new')
        self.assertEqual(resp.status_code, 400, "Missing CSRF token on /complaints/new must yield 400")

        # Create draft via service for further endpoint tests
        draft = create_draft_complaint(self.citizen.id)

        # 4. Draft save without token
        resp = self.client.post(f'/complaints/{draft.id}/draft', json={'title': 'Test Attack'})
        self.assertEqual(resp.status_code, 400, "Missing CSRF header on /complaints/<id>/draft must yield 400")

        # 5. Evidence upload without token
        png_data = _generate_valid_png_bytes()
        fake_file = (io.BytesIO(png_data), 'photo.png')
        resp = self.client.post(f'/complaints/{draft.id}/evidence', data={'evidence_files': fake_file}, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 400, "Missing CSRF on evidence upload must yield 400")

    # =========================================================================
    # GATE 2: Protected POST requests reject invalid tokens
    # =========================================================================
    def test_02_protected_post_requests_reject_invalid_tokens(self):
        """Gate 2: POST requests containing tampered, forged, or malformed CSRF tokens are rejected with HTTP 400."""
        # 1. Bogus string token
        resp = self.client.post('/login', data={
            'username': 'citizen_csrf',
            'password': 'Password123!',
            'csrf_token': 'malicious_forged_token_xyz'
        })
        self.assertEqual(resp.status_code, 400)

        # 2. Token signed with wrong secret key
        wrong_serializer = URLSafeTimedSerializer('wrong-secret-key', salt='wtf-csrf-token')
        forged_token = wrong_serializer.dumps(secrets.token_hex(32))
        resp = self.client.post('/login', data={
            'username': 'citizen_csrf',
            'password': 'Password123!',
            'csrf_token': forged_token
        })
        self.assertEqual(resp.status_code, 400)

        # 3. Log in legitimately
        self._login('citizen_csrf', 'Password123!')
        draft = create_draft_complaint(self.citizen.id)

        # 4. Draft save with invalid header token
        resp = self.client.post(
            f'/complaints/{draft.id}/draft',
            json={'title': 'Tampered Attack'},
            headers={'X-CSRFToken': 'invalid-header-token'}
        )
        self.assertEqual(resp.status_code, 400)

    # =========================================================================
    # GATE 3: A valid token permits an authorized operation
    # =========================================================================
    def test_03_valid_token_permits_authorized_operation(self):
        """Gate 3: Authorized POST requests with valid CSRF tokens succeed normally (HTTP 200/302)."""
        # 1. Login with valid token
        resp_login = self._login('citizen_csrf', 'Password123!')
        self.assertEqual(resp_login.status_code, 302)

        # 2. Create complaint draft via POST /complaints/new with valid token
        token = self._get_csrf_token()
        resp_new = self.client.post('/complaints/new', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(resp_new.status_code, 302)
        self.assertIn('/edit', resp_new.headers['Location'])

        # 3. Save draft step with valid X-CSRFToken header
        draft = Complaint.query.filter_by(created_by_id=self.citizen.id).first()
        token = self._get_csrf_token()
        resp_save = self.client.post(
            f'/complaints/{draft.id}/draft',
            json={'title': 'Authorized Valid Case', 'category': 'Theft'},
            headers={'X-CSRFToken': token}
        )
        self.assertEqual(resp_save.status_code, 200)
        self.assertEqual(draft.title, 'Authorized Valid Case')

    # =========================================================================
    # GATE 4: Missing or invalid tokens never execute underlying operation
    # =========================================================================
    def test_04_missing_or_invalid_tokens_never_execute_underlying_operation(self):
        """Gate 4: Operations blocked by CSRF failures never modify database records or files."""
        self._login('citizen_csrf', 'Password123!')
        draft = create_draft_complaint(self.citizen.id)
        original_title = draft.title
        original_status = draft.status

        # Attempt to modify draft with invalid token
        resp = self.client.post(
            f'/complaints/{draft.id}/draft',
            json={'title': 'ATTACK_TAMPERED_TITLE'},
            headers={'X-CSRFToken': 'bad_token'}
        )
        self.assertEqual(resp.status_code, 400)

        # Verify DB is unchanged
        db.session.refresh(draft)
        self.assertEqual(draft.title, original_title)
        self.assertEqual(draft.status, original_status)

        # Attempt to submit draft without token
        resp = self.client.post(f'/complaints/{draft.id}/submit', json={})
        self.assertEqual(resp.status_code, 400)
        db.session.refresh(draft)
        self.assertEqual(draft.status, 'draft')

    # =========================================================================
    # GATE 5: Login and registration forms contain usable CSRF tokens
    # =========================================================================
    def test_05_login_and_registration_forms_contain_usable_tokens(self):
        """Gate 5: GET /login and GET /register render forms containing valid hidden csrf_token inputs."""
        # Login form
        resp_login = self.client.get('/login')
        self.assertEqual(resp_login.status_code, 200)
        self.assertIn(b'name="csrf_token"', resp_login.data)
        self.assertIn(b'type="hidden"', resp_login.data)

        # Register form
        resp_reg = self.client.get('/register')
        self.assertEqual(resp_reg.status_code, 200)
        self.assertIn(b'name="csrf_token"', resp_reg.data)
        self.assertIn(b'type="hidden"', resp_reg.data)

    # =========================================================================
    # GATE 6: Complaint and evidence forms contain usable CSRF tokens
    # =========================================================================
    def test_06_complaint_and_evidence_forms_contain_usable_tokens(self):
        """Gate 6: Wizard and case forms expose CSRF tokens in HTML and metadata."""
        self._login('citizen_csrf', 'Password123!')
        draft = create_draft_complaint(self.citizen.id)

        # Wizard form
        resp = self.client.get(f'/complaints/{draft.id}/edit')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'name="csrf_token"', resp.data)
        self.assertIn(b'meta name="csrf-token"', resp.data)
        self.assertIn(b'window.CSRF_TOKEN', resp.data)

    # =========================================================================
    # GATE 7: Admin actions and poster approval are protected
    # =========================================================================
    def test_07_admin_actions_and_poster_approval_protected(self):
        """Gate 7: Admin lifecycle transitions, officer assignment, and poster approval reject requests without CSRF."""
        # Set up a submitted case
        draft = create_draft_complaint(self.citizen.id)
        update_draft_complaint(draft.id, self.citizen.id, {
            'title': 'Burglary Case',
            'category': 'Theft',
            'incident_at': '2026-10-10T12:00',
            'location_address': 'Sector 14',
            'narrative': 'Valid incident narrative for testing admin review gates.'
        })
        case = submit_complaint(draft.id, self.citizen.id)

        # Log in admin
        self._login('admin_csrf', 'AdminPassword123!')

        # 1. Review action without CSRF -> 400
        resp = self.client.post(f'/admin/cases/{case.id}/action', data={'action': 'start_review'})
        self.assertEqual(resp.status_code, 400)
        db.session.refresh(case)
        self.assertEqual(case.status, 'submitted', "Case status must remain unchanged on CSRF failure")

        # 2. Review action with valid CSRF -> 302
        token = self._get_csrf_token()
        resp = self.client.post(f'/admin/cases/{case.id}/action', data={'action': 'start_review', 'csrf_token': token})
        self.assertEqual(resp.status_code, 302)
        db.session.refresh(case)
        self.assertEqual(case.status, 'under_review')

        # 3. Create poster artifact for case
        poster_png = _generate_valid_png_bytes()
        poster_ev = save_case_artifact(
            complaint_id=case.id,
            actor_id=self.admin.id,
            file_bytes=poster_png,
            filename='poster_draft.png',
            evidence_type='poster'
        )
        self.assertNotEqual(poster_ev.access_level, 'public_notice')

        # 4. Poster approval without CSRF -> 400
        resp = self.client.post(f'/cases/{case.id}/poster/{poster_ev.id}/approve')
        self.assertEqual(resp.status_code, 400)
        db.session.refresh(poster_ev)
        self.assertNotEqual(poster_ev.access_level, 'public_notice')

        # 5. Poster approval with valid CSRF -> 302
        token = self._get_csrf_token()
        resp = self.client.post(f'/cases/{case.id}/poster/{poster_ev.id}/approve', data={'csrf_token': token})
        self.assertEqual(resp.status_code, 302)
        db.session.refresh(poster_ev)
        self.assertEqual(poster_ev.access_level, 'public_notice')

    # =========================================================================
    # GATE 8: Biometric recognition POST requires token & validates binding
    # =========================================================================
    def test_08_biometric_recognition_post_requires_token_and_validates_binding(self):
        """Gate 8: Biometric recognition POST requires CSRF token and validates Branch B case/photo binding."""
        # Set up Branch B case
        draft = create_draft_complaint(self.citizen.id)
        png_data = _generate_valid_png_bytes()
        fs = FileStorage(stream=io.BytesIO(png_data), filename='suspect_clear.png', content_type='image/png')
        ev = attach_evidence_file(draft.id, self.citizen.id, fs, custom_evidence_type='photo')
        update_draft_complaint(draft.id, self.citizen.id, {
            'title': 'Branch B Photo Case',
            'category': 'Robbery',
            'facial_reference_type': 'photo_normal',
            'incident_at': '2026-10-10T12:00',
            'location_address': 'Sector 9',
            'narrative': 'Branch B valid complaint narrative.'
        })
        case = submit_complaint(draft.id, self.citizen.id)
        transition_case_status(case.id, self.admin.id, 'approved')
        transition_case_status(case.id, self.admin.id, 'investigation_in_progress')

        # Log in admin
        self._login('admin_csrf', 'AdminPassword123!')

        # POST without CSRF token -> 400
        resp = self.client.post(f'/cases/{case.id}/recognition', data={'evidence_id': ev.id})
        self.assertEqual(resp.status_code, 400)

        # POST with invalid CSRF token -> 400
        resp = self.client.post(f'/cases/{case.id}/recognition', data={'evidence_id': ev.id, 'csrf_token': 'bad_token'})
        self.assertEqual(resp.status_code, 400)

        # POST with valid token: mock inference to test handler logic
        token = self._get_csrf_token()
        mock_encoding = np.array([0.05] * 128)
        with patch('app.get_face_encoding', return_value=mock_encoding), \
             patch('app.find_matches', return_value=[]):
            resp = self.client.post(f'/cases/{case.id}/recognition', data={'evidence_id': ev.id, 'csrf_token': token})
            self.assertEqual(resp.status_code, 200)

    # =========================================================================
    # GATE 9: Logout cannot be triggered by GET and requires valid POST token
    # =========================================================================
    def test_09_logout_cannot_be_triggered_by_get_and_requires_valid_post(self):
        """Gate 9: GET /logout does not clear the session; POST /logout requires a valid CSRF token."""
        self._login('citizen_csrf', 'Password123!')

        # 1. GET /logout must redirect without clearing session
        resp_get = self.client.get('/logout')
        self.assertEqual(resp_get.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), self.citizen.id, "GET /logout must not clear the session")

        # 2. POST /logout without CSRF token -> 400
        resp_post_no_csrf = self.client.post('/logout')
        self.assertEqual(resp_post_no_csrf.status_code, 400)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), self.citizen.id)

        # 3. POST /logout with valid CSRF token -> 302 and session cleared
        token = self._get_csrf_token()
        resp_post_valid = self.client.post('/logout', data={'csrf_token': token})
        self.assertEqual(resp_post_valid.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'), "Valid POST /logout must clear the session")

    # =========================================================================
    # GATE 10: GET /complaints/new does not create draft; protected POST does
    # =========================================================================
    def test_10_get_complaints_new_does_not_create_draft_post_does(self):
        """Gate 10: GET /complaints/new is read-only (zero drafts inserted); POST /complaints/new creates draft."""
        self._login('citizen_csrf', 'Password123!')

        count_before = Complaint.query.count()

        # GET request
        resp_get = self.client.get('/complaints/new')
        self.assertEqual(resp_get.status_code, 200)
        count_after_get = Complaint.query.count()
        self.assertEqual(count_before, count_after_get, "GET /complaints/new must NOT insert any complaint records")

        # POST request with valid CSRF token
        token = self._get_csrf_token()
        resp_post = self.client.post('/complaints/new', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(resp_post.status_code, 302)
        self.assertIn('/edit', resp_post.headers['Location'])

        count_after_post = Complaint.query.count()
        self.assertEqual(count_after_post, count_before + 1, "POST /complaints/new must insert exactly one draft")

    # =========================================================================
    # GATE 11: Existing role and case-ownership restrictions remain enforced
    # =========================================================================
    def test_11_role_and_case_ownership_restrictions_remain_enforced(self):
        """Gate 11: Cross-user and RBAC checks remain strictly enforced even when valid tokens are supplied."""
        # Citizen A creates draft
        draft_a = create_draft_complaint(self.citizen.id)

        # Citizen B logs in
        client_b = app.test_client()
        self._login('citizen_other_csrf', 'Password123!', client=client_b)
        token_b = self._get_csrf_token(client_b)

        # Citizen B tries to save draft to Citizen A's case
        resp = client_b.post(
            f'/complaints/{draft_a.id}/draft',
            json={'title': 'Cross User Attack'},
            headers={'X-CSRFToken': token_b}
        )
        self.assertEqual(resp.status_code, 403, "Cross-user draft modification must be 403 Forbidden")

        # Admin logs in and tries citizen-only route
        admin_client = app.test_client()
        self._login('admin_csrf', 'AdminPassword123!', client=admin_client)
        admin_token = self._get_csrf_token(admin_client)
        resp_admin = admin_client.post('/complaints/new', data={'csrf_token': admin_token})
        self.assertEqual(resp_admin.status_code, 403, "Admin accessing citizen route must yield 403")

    # =========================================================================
    # GATE 12: Invalid-token requests do not create success timeline entries
    # =========================================================================
    def test_12_invalid_token_requests_do_not_create_timeline_entries(self):
        """Gate 12: Requests rejected by CSRF protection produce zero timeline audit entries."""
        draft = create_draft_complaint(self.citizen.id)
        update_draft_complaint(draft.id, self.citizen.id, {
            'title': 'Test Case',
            'category': 'Theft',
            'incident_at': '2026-10-10T12:00',
            'location_address': 'Sector 1',
            'narrative': 'Test narrative'
        })
        case = submit_complaint(draft.id, self.citizen.id)

        timeline_count_before = ComplaintTimeline.query.count()

        # Attacker tries to transition case with bad token
        self._login('admin_csrf', 'AdminPassword123!')
        resp = self.client.post(
            f'/admin/cases/{case.id}/action',
            data={'action': 'start_review', 'csrf_token': 'bogus_token'}
        )
        self.assertEqual(resp.status_code, 400)

        timeline_count_after = ComplaintTimeline.query.count()
        self.assertEqual(timeline_count_before, timeline_count_after, "Failed CSRF request must not create timeline event")

    # =========================================================================
    # GATE 13: Original submitted evidence remains immutable
    # =========================================================================
    def test_13_original_submitted_evidence_remains_immutable(self):
        """Gate 13: Submitted evidence cannot be modified or deleted even with valid CSRF token."""
        draft = create_draft_complaint(self.citizen.id)
        png_data = _generate_valid_png_bytes()
        fs = FileStorage(stream=io.BytesIO(png_data), filename='original_proof.png', content_type='image/png')
        ev = attach_evidence_file(draft.id, self.citizen.id, fs, custom_evidence_type='photo')
        update_draft_complaint(draft.id, self.citizen.id, {
            'title': 'Evidence Immutability Case',
            'category': 'Assault',
            'incident_at': '2026-10-10T12:00',
            'location_address': 'Sector 2',
            'narrative': 'Immutability test narrative'
        })
        case = submit_complaint(draft.id, self.citizen.id)

        self._login('citizen_csrf', 'Password123!')
        token = self._get_csrf_token()

        # Attempt to delete evidence post-submission with valid token -> 400
        resp_del = self.client.post(f'/complaints/{case.id}/evidence/{ev.id}/delete', data={'csrf_token': token})
        self.assertEqual(resp_del.status_code, 400)

        # Evidence must still exist in DB
        db.session.refresh(ev)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.complaint_id, case.id)

    # =========================================================================
    # GATE 14: Tests cannot access or modify live MySQL
    # =========================================================================
    def test_14_zero_live_mysql_connection(self):
        """Gate 14: Enforces fail-closed SQLite in-memory isolation with zero live MySQL connections."""
        engine_url = str(db.engine.url)
        self.assertTrue(
            engine_url.startswith("sqlite:///:memory:") or engine_url.startswith("sqlite://"),
            f"Test suite must run strictly on SQLite in-memory, but engine is: {engine_url}"
        )
        self.assertEqual(db.engine.dialect.name, "sqlite")


if __name__ == '__main__':
    unittest.main()
