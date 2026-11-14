"""
test_phase5_1_biometric_case_binding.py — ThirdEye Phase 5.1 Automated Test Suite
================================================================================
Verifies Biometric Recognition Case-Binding, Evidence Eligibility, and Zero-Upload Workflow:

Covers all 10 required Phase 5.1 verification gates:
 1. An authorized Branch B case can execute recognition against its eligible original photograph.
 2. The case-linked form does not require a second arbitrary image upload.
 3. A caller cannot substitute a sketch, reconstructed face, or variation; Option C is rejected.
 4. An evidence ID from another case is rejected.
 5. An unapproved or otherwise ineligible case cannot execute recognition.
 6. The standalone recognition route cannot bypass case authorization.
 7. A failed recognition operation reports failure rather than fabricating a match.
 8. Recognition results and audit entries, if recorded, are associated with the correct case and source.
 9. Submitted original evidence remains unchanged.
 10. Tests cannot connect to or modify live MySQL.
"""

import os
import sys

# Windows Anaconda DLL loading
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

import unittest
import io
import shutil
import tempfile
import numpy as np
import cv2
from datetime import datetime
from unittest.mock import patch, MagicMock

os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
os.environ["TESTING"] = "True"

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
    save_case_artifact,
    get_eligible_recognition_evidence,
    validate_recognition_source_evidence
)


def _generate_valid_png_bytes(width=100, height=100, color=(140, 160, 200)):
    """Generates valid PNG image bytes for testing."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    _, buf = cv2.imencode('.png', img)
    return buf.tobytes()


class Phase51BiometricCaseBindingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.test_storage_root = tempfile.mkdtemp(prefix="thirdeye_phase5_1_test_storage_")
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

        # Provision synthetic users
        self.user_a = User(username='citizen_alice_p51', password='Password123!', role='user', full_name='Alice Citizen')
        self.user_b = User(username='citizen_bob_p51', password='Password123!', role='user', full_name='Bob Citizen')
        self.admin_user = User(username='admin_inspector_p51', password='AdminPassword123!', role='admin', full_name='Inspector Admin')
        db.session.add_all([self.user_a, self.user_b, self.admin_user])

        # Provision enrolled suspect person
        self.enrolled_person = Person(
            name='Suspect X',
            person_details='Wanted for commercial burglary',
            image_path='person_x.jpg',
            face_encoding=','.join(['0.05'] * 128)
        )
        db.session.add(self.enrolled_person)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, user):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['username'] = user.username
            sess['role'] = user.role
            sess['full_name'] = user.full_name

    def _create_branch_b_case(self, user, filename='authentic_suspect_cctv.png'):
        """Creates an approved Branch B case with an authentic uploaded photograph."""
        complaint = create_draft_complaint(user.id)
        update_draft_complaint(complaint.id, user.id, {
            'title': 'CCTV Commercial Robbery',
            'category': 'Robbery',
            'incident_datetime': '2026-10-11T12:00',
            'incident_location': '104 Anna Salai, Chennai',
            'narrative': 'High-resolution store camera captured suspect unmasked.',
            'facial_reference_type': 'photo_normal',
            'suspect_gender': 'Male',
            'suspect_approx_age': '30'
        })
        png_bytes = _generate_valid_png_bytes(120, 120, color=(160, 180, 210))
        dummy_file = io.BytesIO(png_bytes)
        dummy_file.filename = filename
        from werkzeug.datastructures import FileStorage
        fs = FileStorage(stream=dummy_file, filename=filename, content_type='image/png')
        attach_evidence_file(complaint.id, user.id, fs)

        submitted = submit_complaint(complaint.id, user.id)
        transition_case_status(submitted.id, self.admin_user.id, 'under_review')
        transition_case_status(submitted.id, self.admin_user.id, 'approved')
        return submitted

    # -------------------------------------------------------------------------
    # Gate 1: Authorized Branch B case executes recognition against eligible photo
    # -------------------------------------------------------------------------
    def test_01_authorized_branch_b_executes_recognition_against_original_photo(self):
        """Gate 1: Authorized Branch B case executes biometric recognition against its eligible original photograph."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)

        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()
        self.assertIsNotNone(photo_ev)

        # GET request renders recognition page with case metadata and NO file picker
        resp_get = self.client.get(f'/cases/{case_b.id}/recognition')
        self.assertEqual(resp_get.status_code, 200)
        html_get = resp_get.data.decode('utf-8')
        self.assertIn(case_b.complaint_number, html_get)
        self.assertIn(photo_ev.original_filename, html_get)
        self.assertIn(photo_ev.sha256_hex[:24], html_get)
        self.assertNotIn('type="file"', html_get, "Arbitrary file upload control found on case-linked recognition screen!")
        self.assertNotIn('name="sketch"', html_get)

        # POST executes recognition on the existing server-side evidence
        mock_encoding = np.array([0.05] * 128)
        mock_matches = [{'person': self.enrolled_person, 'similarity': 92.5}]

        with patch('app.get_face_encoding', return_value=mock_encoding), \
             patch('app.find_matches', return_value=mock_matches):
            resp_post = self.client.post(
                f'/cases/{case_b.id}/recognition',
                data={'evidence_id': photo_ev.id}
            )
            self.assertEqual(resp_post.status_code, 200)
            html_post = resp_post.data.decode('utf-8')
            self.assertIn('Candidate Record Matches Found', html_post)
            self.assertIn('Suspect X', html_post)
            self.assertIn('92.5%', html_post)
            self.assertIn('Forensic Biometric Advisory &amp; Mandatory Human Review', html_post)

    # -------------------------------------------------------------------------
    # Gate 2: Case-linked form does not require a second arbitrary image upload
    # -------------------------------------------------------------------------
    def test_02_case_linked_form_does_not_require_second_upload(self):
        """Gate 2: Case-linked recognition executes with zero client-supplied file uploads."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)

        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        mock_encoding = np.array([0.05] * 128)
        mock_matches = [{'person': self.enrolled_person, 'similarity': 88.0}]

        with patch('app.get_face_encoding', return_value=mock_encoding), \
             patch('app.find_matches', return_value=mock_matches):
            # Send POST with strictly empty files dictionary
            resp = self.client.post(
                f'/cases/{case_b.id}/recognition',
                data={'evidence_id': photo_ev.id}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Candidate Record Matches Found', resp.data)

    # -------------------------------------------------------------------------
    # Gate 3: Caller cannot substitute sketch, reconstruction, variation, or masked illustration
    # -------------------------------------------------------------------------
    def test_03_substituting_sketch_reconstruction_variation_or_masked_photo_rejected(self):
        """Gate 3: System rejects sketches, reconstructions, variations, or masked photos passed as recognition source."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)

        # 1. Add derived variation artifact to Case B
        var_ev = save_case_artifact(
            complaint_id=case_b.id,
            actor_id=self.user_a.id,
            file_bytes=_generate_valid_png_bytes(100, 100),
            filename='speculative_variation.png',
            evidence_type='variation'
        )

        # Attempt to run recognition using the variation artifact ID -> rejected
        resp_var = self.client.post(
            f'/cases/{case_b.id}/recognition',
            data={'evidence_id': var_ev.id},
            follow_redirects=False
        )
        self.assertEqual(resp_var.status_code, 302)
        # Redirects back to recognition with flash warning
        self.assertIn(f'/cases/{case_b.id}/recognition', resp_var.headers['Location'])

        # 2. Discontinued Option C ('photo_masked') is rejected server-side
        case_c = create_draft_complaint(self.user_a.id)
        with self.assertRaises(ValueError):
            update_draft_complaint(case_c.id, self.user_a.id, {
                'title': 'Masked Suspect Case',
                'category': 'Theft',
                'narrative': 'Masked suspect entered building.',
                'facial_reference_type': 'photo_masked'
            })

    # -------------------------------------------------------------------------
    # Gate 4: An evidence ID from another case is rejected
    # -------------------------------------------------------------------------
    def test_04_cross_case_evidence_id_rejected(self):
        """Gate 4: An evidence ID belonging to another case is safely rejected server-side."""
        case_1 = self._create_branch_b_case(self.user_a, filename='photo_case1.png')
        case_2 = self._create_branch_b_case(self.user_b, filename='photo_case2.png')

        photo_2 = case_2.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()
        self.assertIsNotNone(photo_2)

        # User A tries to invoke recognition on Case 1 using photo_2 from Case 2
        self._login(self.user_a)
        resp = self.client.post(
            f'/cases/{case_1.id}/recognition',
            data={'evidence_id': photo_2.id},
            follow_redirects=False
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_1.id}/recognition', resp.headers['Location'])

        # Follow redirect and verify error flash message
        resp_followed = self.client.get(f'/cases/{case_1.id}/recognition')
        self.assertIn(b'Invalid recognition source evidence', resp_followed.data)

    # -------------------------------------------------------------------------
    # Gate 5: An unapproved or otherwise ineligible case cannot execute recognition
    # -------------------------------------------------------------------------
    def test_05_unapproved_or_ineligible_case_cannot_execute_recognition(self):
        """Gate 5: An unapproved case (e.g. status='submitted' or 'under_review') cannot execute recognition."""
        from werkzeug.datastructures import FileStorage
        case_b = create_draft_complaint(self.user_a.id)
        update_draft_complaint(case_b.id, self.user_a.id, {
            'title': 'Intake Stage Robbery',
            'category': 'Robbery',
            'narrative': 'Robbery intake narrative.',
            'facial_reference_type': 'photo_normal'
        })
        fs = FileStorage(stream=io.BytesIO(_generate_valid_png_bytes()), filename='cctv.png', content_type='image/png')
        attach_evidence_file(case_b.id, self.user_a.id, fs)
        submitted = submit_complaint(case_b.id, self.user_a.id)

        self._login(self.user_a)
        # Status is 'submitted' -> not approved
        resp = self.client.get(f'/cases/{submitted.id}/recognition', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{submitted.id}/workspace', resp.headers['Location'])

    # -------------------------------------------------------------------------
    # Gate 6: Standalone recognition route cannot bypass case authorization
    # -------------------------------------------------------------------------
    def test_06_standalone_recognition_route_cannot_bypass_case_authorization(self):
        """Gate 6: Standalone /recognition route redirects safely and blocks unauthorized access."""
        case_b = self._create_branch_b_case(self.user_a)

        # 1. Without complaint_id -> redirects to citizen complaints with advisory
        self._login(self.user_a)
        resp_direct = self.client.get('/recognition', follow_redirects=False)
        self.assertEqual(resp_direct.status_code, 302)
        self.assertIn('/my-complaints', resp_direct.headers['Location'])

        # 2. Citizen B attempting to pass Case A reference to /recognition -> 403 Forbidden
        self._login(self.user_b)
        resp_unauth = self.client.get(f'/recognition?complaint_id={case_b.id}')
        self.assertEqual(resp_unauth.status_code, 403)

    # -------------------------------------------------------------------------
    # Gate 7: Failed recognition operation reports failure rather than fabricating a match
    # -------------------------------------------------------------------------
    def test_07_failed_recognition_operation_reports_failure_without_fabricating_match(self):
        """Gate 7: If face detection fails, the system reports clear error without fabricating matches or timeline."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        tl_initial = case_b.timeline.count()

        # Mock face detection failing (no face found in photo)
        with patch('app.get_face_encoding', return_value=None):
            resp = self.client.post(
                f'/cases/{case_b.id}/recognition',
                data={'evidence_id': photo_ev.id}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Face Detection Limitation', resp.data)
            self.assertIn(b'No detectable human face found', resp.data)
            self.assertNotIn(b'Candidate Record Matches Found', resp.data)

        # Verify no false timeline entry recorded
        self.assertEqual(case_b.timeline.count(), tl_initial)

    # -------------------------------------------------------------------------
    # Gate 8: Recognition results and audit entries are associated with correct case and source
    # -------------------------------------------------------------------------
    def test_08_recognition_results_and_audit_entries_associated_with_correct_case_and_source(self):
        """Gate 8: Timeline audit entry specifically references the case and source evidence ID."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        mock_encoding = np.array([0.05] * 128)
        mock_matches = [{'person': self.enrolled_person, 'similarity': 75.0}]

        with patch('app.get_face_encoding', return_value=mock_encoding), \
             patch('app.find_matches', return_value=mock_matches):
            self.client.post(
                f'/cases/{case_b.id}/recognition',
                data={'evidence_id': photo_ev.id}
            )

        tl = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='recognition_performed'
        ).order_by(ComplaintTimeline.id.desc()).first()

        self.assertIsNotNone(tl)
        self.assertEqual(tl.actor_user_id, self.user_a.id)
        self.assertIn(f"evidence #{photo_ev.id}", tl.message)
        self.assertIn(photo_ev.original_filename, tl.message)

    # -------------------------------------------------------------------------
    # Gate 9: Submitted original evidence remains unchanged
    # -------------------------------------------------------------------------
    def test_09_submitted_original_evidence_remains_unchanged(self):
        """Gate 9: The authentic uploaded photograph record and hash remain completely invariant."""
        case_b = self._create_branch_b_case(self.user_a)
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()
        initial_hash = photo_ev.sha256_hex
        initial_size = photo_ev.file_size_bytes

        self._login(self.user_a)
        mock_encoding = np.array([0.05] * 128)
        mock_matches = [{'person': self.enrolled_person, 'similarity': 80.0}]

        with patch('app.get_face_encoding', return_value=mock_encoding), \
             patch('app.find_matches', return_value=mock_matches):
            self.client.post(
                f'/cases/{case_b.id}/recognition',
                data={'evidence_id': photo_ev.id}
            )

        photo_after = ComplaintEvidence.query.get(photo_ev.id)
        self.assertEqual(photo_after.sha256_hex, initial_hash)
        self.assertEqual(photo_after.file_size_bytes, initial_size)

    # -------------------------------------------------------------------------
    # Gate 10: Tests cannot connect to or modify live MySQL
    # -------------------------------------------------------------------------
    def test_10_zero_live_mysql_connection(self):
        """Gate 10: Enforces fail-closed SQLite in-memory isolation with zero live MySQL connections."""
        dialect = db.engine.dialect.name
        self.assertEqual(dialect, 'sqlite')
        db_uri = str(db.engine.url)
        self.assertTrue('sqlite' in db_uri and ':memory:' in db_uri)

    # -------------------------------------------------------------------------
    # Gate 11: GET renders the recognition page without running recognition engine
    # -------------------------------------------------------------------------
    def test_11_get_renders_page_without_running_recognition_engine(self):
        """Gate 11: GET /cases/<id>/recognition renders the UI without executing face encoding or matching."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)
        tl_initial = case_b.timeline.count()

        with patch('app.get_face_encoding') as mock_enc, \
             patch('app.find_matches') as mock_match:
            resp = self.client.get(f'/cases/{case_b.id}/recognition')
            self.assertEqual(resp.status_code, 200)
            mock_enc.assert_not_called()
            mock_match.assert_not_called()
            self.assertIn(b'Ready for Biometric Search', resp.data)
            self.assertNotIn(b'Candidate Record Matches Found', resp.data)

        self.assertEqual(case_b.timeline.count(), tl_initial)

    # -------------------------------------------------------------------------
    # Gate 12: GET with ?execute=1 cannot execute recognition
    # -------------------------------------------------------------------------
    def test_12_get_with_execute_1_cannot_execute_recognition(self):
        """Gate 12: GET with ?execute=1 is strictly rejected from initiating biometric recognition."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)
        tl_initial = case_b.timeline.count()

        with patch('app.get_face_encoding') as mock_enc, \
             patch('app.find_matches') as mock_match:
            resp = self.client.get(f'/cases/{case_b.id}/recognition?execute=1')
            self.assertEqual(resp.status_code, 200)
            mock_enc.assert_not_called()
            mock_match.assert_not_called()
            self.assertIn(b'Ready for Biometric Search', resp.data)
            self.assertNotIn(b'Candidate Record Matches Found', resp.data)

        self.assertEqual(case_b.timeline.count(), tl_initial)

    # -------------------------------------------------------------------------
    # Gate 13: Neither GET variant creates a recognition_performed event
    # -------------------------------------------------------------------------
    def test_13_neither_get_variant_creates_recognition_performed_event(self):
        """Gate 13: Neither plain GET nor GET with ?execute=1 creates any ComplaintTimeline event."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        # Variant A: Standard GET
        self.client.get(f'/cases/{case_b.id}/recognition')
        count_a = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='recognition_performed'
        ).count()
        self.assertEqual(count_a, 0)

        # Variant B: GET with execute=1
        self.client.get(f'/cases/{case_b.id}/recognition?execute=1')
        count_b = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='recognition_performed'
        ).count()
        self.assertEqual(count_b, 0)

        # Variant C: GET with execute=1 and explicit evidence_id
        self.client.get(f'/cases/{case_b.id}/recognition?execute=1&evidence_id={photo_ev.id}')
        count_c = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='recognition_performed'
        ).count()
        self.assertEqual(count_c, 0)

    # -------------------------------------------------------------------------
    # Gate 14: Unauthorized users cannot initiate recognition via POST
    # -------------------------------------------------------------------------
    def test_14_unauthorized_users_cannot_initiate_recognition_via_post(self):
        """Gate 14: Unauthenticated users and unauthorized cross-users cannot initiate recognition via POST."""
        case_b = self._create_branch_b_case(self.user_a)
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        # 1. Unauthenticated request -> redirects to login
        unauth_client = app.test_client()
        resp_unauth = unauth_client.post(
            f'/cases/{case_b.id}/recognition',
            data={'evidence_id': photo_ev.id},
            follow_redirects=False
        )
        self.assertEqual(resp_unauth.status_code, 302)
        self.assertIn('/login', resp_unauth.headers['Location'])

        # 2. Citizen Bob attempting to post to Citizen Alice's case -> 403 Forbidden
        self._login(self.user_b)
        resp_cross = self.client.post(
            f'/cases/{case_b.id}/recognition',
            data={'evidence_id': photo_ev.id}
        )
        self.assertEqual(resp_cross.status_code, 403)

        # Confirm zero timeline entries created
        tl_count = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='recognition_performed'
        ).count()
        self.assertEqual(tl_count, 0)

    # -------------------------------------------------------------------------
    # Gate 15: POST missing evidence_id or invalid ID safely rejected
    # -------------------------------------------------------------------------
    def test_15_post_missing_or_invalid_evidence_id_rejected(self):
        """Gate 15: POST without evidence_id or with an invalid evidence ID is rejected safely."""
        case_b = self._create_branch_b_case(self.user_a)
        self._login(self.user_a)

        # 1. Missing evidence_id
        resp_missing = self.client.post(
            f'/cases/{case_b.id}/recognition',
            data={},
            follow_redirects=False
        )
        self.assertEqual(resp_missing.status_code, 302)
        self.assertIn(f'/cases/{case_b.id}/recognition', resp_missing.headers['Location'])

        # 2. Non-existent evidence_id
        resp_invalid = self.client.post(
            f'/cases/{case_b.id}/recognition',
            data={'evidence_id': 999999},
            follow_redirects=False
        )
        self.assertEqual(resp_invalid.status_code, 302)
        self.assertIn(f'/cases/{case_b.id}/recognition', resp_invalid.headers['Location'])

        tl_count = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='recognition_performed'
        ).count()
        self.assertEqual(tl_count, 0)


if __name__ == '__main__':
    unittest.main()
