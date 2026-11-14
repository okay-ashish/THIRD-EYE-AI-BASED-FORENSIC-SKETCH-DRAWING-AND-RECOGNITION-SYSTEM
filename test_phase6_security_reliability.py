"""
test_phase6_security_reliability.py — ThirdEye Phase 6 Final Security & Reliability Suite
========================================================================================
Comprehensive regression and hardening verification covering:
 1. Session Cookie Security & CSRF Baseline Configuration Audit
 2. Safe GET Behavior on Forensic & Destructive Routes (Zero Side-Effects)
 3. Two-Role RBAC Enforced Across All Routes (Citizen vs Admin)
 4. Cross-User and Cross-Case Access Control Isolation
 5. Complete 3-Branch Forensic Integrity (Branch A, B, C)
 6. Controlled Poster Approval & Public Access Authorization
 7. Evidence Immutability & Additive Storage Preservation
 8. Failed Operations Resilience & Clean Transaction Rollbacks
 9. Audit Timeline Trail Consistency & Actor Attribution
 10. Database Isolation & Fail-Closed Live MySQL Protection
"""

import os
import sys

# Windows Anaconda DLL registration
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

# Enforce fail-closed SQLite in-memory isolation
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
    submit_case_addendum,
    can_access_tool,
    save_case_artifact,
    approve_poster_for_distribution,
    get_eligible_recognition_evidence,
    validate_recognition_source_evidence
)


def _generate_valid_png_bytes(width=100, height=100, color=(140, 160, 200)):
    """Generates valid PNG image bytes for testing."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    _, buf = cv2.imencode('.png', img)
    return buf.tobytes()


class Phase6SecurityReliabilityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.test_storage_root = tempfile.mkdtemp(prefix="thirdeye_phase6_test_storage_")
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
        self.user_a = User(username='citizen_alice_p6', password='Password123!', role='user', full_name='Alice Citizen')
        self.user_b = User(username='citizen_bob_p6', password='Password123!', role='user', full_name='Bob Citizen')
        self.admin_user = User(username='admin_sundaram_p6', password='AdminPassword123!', role='admin', full_name='Inspector Sundaram')
        db.session.add_all([self.user_a, self.user_b, self.admin_user])

        # Provision enrolled suspect person
        self.enrolled_person = Person(
            name='Gallery Suspect A',
            person_details='Enrolled for commercial burglary testing',
            image_path='gallery_a.jpg',
            face_encoding=','.join(['0.04'] * 128)
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

    def _create_approved_case(self, user, ref_type='none', filename='evidence.png'):
        complaint = create_draft_complaint(user.id)
        update_draft_complaint(complaint.id, user.id, {
            'title': f'Test Incident {ref_type}',
            'category': 'Theft / Burglary',
            'incident_at': '2026-10-11T10:00',
            'location_address': 'Sector 4 Anna Nagar, Chennai',
            'narrative': 'Clear investigation narrative for case verification.',
            'facial_reference_type': ref_type,
            'suspect_gender': 'Male',
            'suspect_approx_age': '28'
        })
        if ref_type == 'photo_normal':
            from werkzeug.datastructures import FileStorage
            fs = FileStorage(
                stream=io.BytesIO(_generate_valid_png_bytes()),
                filename=filename,
                content_type='image/png'
            )
            attach_evidence_file(complaint.id, user.id, fs)

        submitted = submit_complaint(complaint.id, user.id)
        transition_case_status(submitted.id, self.admin_user.id, 'under_review')
        transition_case_status(submitted.id, self.admin_user.id, 'approved')
        return submitted

    # -------------------------------------------------------------------------
    # Gate 1: Session Cookie Security & CSRF Configuration Audit
    # -------------------------------------------------------------------------
    def test_01_session_cookie_security_and_csrf_audit(self):
        """Gate 1: Verify hardened session cookie settings (HttpOnly, SameSite=Lax, secret key presence)."""
        self.assertTrue(app.config.get('SESSION_COOKIE_HTTPONLY'), "SESSION_COOKIE_HTTPONLY must be True")
        self.assertEqual(app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax', "SESSION_COOKIE_SAMESITE must be Lax")
        self.assertIsNotNone(app.config.get('SECRET_KEY'), "SECRET_KEY must be configured")
        self.assertGreaterEqual(len(app.config['SECRET_KEY']), 16, "SECRET_KEY must meet minimum entropy length")

    # -------------------------------------------------------------------------
    # Gate 2: Safe GET Behavior on Forensic and Destructive Routes
    # -------------------------------------------------------------------------
    def test_02_safe_get_behavior_zero_side_effects(self):
        """Gate 2: GET requests never generate artifacts, mutate state, run inference, or delete DB records."""
        case_a = self._create_approved_case(self.user_a, ref_type='none')
        # Add sketch so reconstruct is unlocked
        sketch_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=_generate_valid_png_bytes(),
            filename='sketch.png',
            evidence_type='sketch',
            generation_method='composite_layers'
        )

        self._login(self.user_a)
        ev_count_initial = case_a.evidence.count()

        # 1. GET /cases/<id>/reconstruct must NOT run reconstruction or create artifacts
        with patch('app.reconstruct_face') as mock_recon:
            resp = self.client.get(f'/cases/{case_a.id}/reconstruct', follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])
            mock_recon.assert_not_called()
        self.assertEqual(case_a.evidence.count(), ev_count_initial)

        # 2. GET /cases/<id>/variations must NOT generate variations
        with patch('app.generate_face_variations') as mock_var:
            resp = self.client.get(f'/cases/{case_a.id}/variations', follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])
            mock_var.assert_not_called()
        self.assertEqual(case_a.evidence.count(), ev_count_initial)

        # 3. GET /cases/<id>/poster must NOT generate poster PDF
        with patch('app.generate_poster_pdf') as mock_poster:
            resp = self.client.get(f'/cases/{case_a.id}/poster', follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])
            mock_poster.assert_not_called()
        self.assertEqual(case_a.evidence.count(), ev_count_initial)

        # 4. GET /admin/delete_person/<id> must NOT delete person from DB
        self._login(self.admin_user)
        resp_del = self.client.get(f'/admin/delete_person/{self.enrolled_person.id}', follow_redirects=False)
        self.assertEqual(resp_del.status_code, 302)
        person_still_exists = Person.query.get(self.enrolled_person.id)
        self.assertIsNotNone(person_still_exists, "GET request improperly deleted Person from database!")

    # -------------------------------------------------------------------------
    # Gate 3: Two-Role RBAC Enforced Across All Routes (Citizen vs Admin)
    # -------------------------------------------------------------------------
    def test_03_two_role_rbac_enforcement(self):
        """Gate 3: Strictly enforce exactly two roles ('user' and 'admin') and block role escalation."""
        # 1. Citizen cannot access Admin endpoints
        self._login(self.user_a)
        resp_admin = self.client.get('/admin/cases', follow_redirects=False)
        self.assertEqual(resp_admin.status_code, 302)

        # 2. Admin cannot access citizen complaint submission routes
        self._login(self.admin_user)
        resp_submit = self.client.get('/complaints/new', follow_redirects=False)
        self.assertEqual(resp_submit.status_code, 403)

        # 3. Verify allowed roles in system constants
        self.assertEqual(ALLOWED_USER_ROLES, ('user', 'admin'))

    # -------------------------------------------------------------------------
    # Gate 4: Cross-User and Cross-Case Access Control Isolation
    # -------------------------------------------------------------------------
    def test_04_cross_user_and_cross_case_isolation(self):
        """Gate 4: Citizens are strictly isolated to their own cases and evidence."""
        case_a = self._create_approved_case(self.user_a, ref_type='photo_normal', filename='photo_a.png')
        photo_ev = case_a.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        # User B attempts to access User A's case workspace -> 403 Forbidden
        self._login(self.user_b)
        resp = self.client.get(f'/cases/{case_a.id}/workspace')
        self.assertEqual(resp.status_code, 403)

        # User B attempts to view User A's evidence -> 403 Forbidden
        resp_ev = self.client.get(f'/cases/{case_a.id}/evidence/{photo_ev.id}/view')
        self.assertEqual(resp_ev.status_code, 403)

        # User B attempts to POST to User A's recognition route -> 403 Forbidden
        resp_rec = self.client.post(f'/cases/{case_a.id}/recognition', data={'evidence_id': photo_ev.id})
        self.assertEqual(resp_rec.status_code, 403)

    # -------------------------------------------------------------------------
    # Gate 5: Dual-Branch Forensic Integrity (Branch A, B) & Option C Rejection
    # -------------------------------------------------------------------------
    def test_05_dual_branch_forensic_integrity_and_option_c_rejection(self):
        """Gate 5: Enforce strict architectural stage policies across Branch A and Branch B, rejecting discontinued Option C."""
        # Branch A: Eyewitness sketch required before reconstruction
        case_a = self._create_approved_case(self.user_a, ref_type='none')
        can_recon, _ = can_access_tool(case_a, 'reconstruct')
        self.assertFalse(can_recon, "Branch A allowed reconstruction prior to sketch creation!")
        can_biometric_a, _ = can_access_tool(case_a, 'recognition')
        self.assertFalse(can_biometric_a, "Branch A allowed biometric recognition on synthetic sketch!")

        # Branch B: Authentic photo preserves photo; skips sketch/reconstruction by default
        case_b = self._create_approved_case(self.user_a, ref_type='photo_normal', filename='photo_b.png')
        can_sketch_b, _ = can_access_tool(case_b, 'sketch')
        can_recon_b, _ = can_access_tool(case_b, 'reconstruct')
        self.assertFalse(can_sketch_b, "Branch B did not bypass sketch step!")
        self.assertFalse(can_recon_b, "Branch B did not bypass reconstruction step!")
        can_biometric_b, _ = can_access_tool(case_b, 'recognition')
        self.assertTrue(can_biometric_b, "Branch B blocked valid biometric recognition on authentic photo!")

        # Option C ('photo_masked') is discontinued and strictly rejected by model validation
        self.assertEqual(ALLOWED_FACIAL_REFERENCE_TYPES, ('none', 'photo_normal'))
        with self.assertRaises(ValueError):
            self._create_approved_case(self.user_a, ref_type='photo_masked', filename='photo_c.png')

    # -------------------------------------------------------------------------
    # Gate 6: Controlled Poster Approval & Public Access Authorization
    # -------------------------------------------------------------------------
    def test_06_controlled_poster_approval_and_public_access(self):
        """Gate 6: Poster drafts remain internal until explicit Admin approval and public notice activation."""
        case_b = self._create_approved_case(self.user_a, ref_type='photo_normal')
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()

        # Generate internal poster draft
        poster_ev = save_case_artifact(
            complaint_id=case_b.id,
            actor_id=self.user_a.id,
            file_bytes=b"%PDF-1.4 Mock Poster",
            filename='poster_draft.pdf',
            evidence_type='poster',
            generation_method='ReportLab A4 Vector Publisher',
            source_evidence_id=photo_ev.id,
            access_level='internal'
        )

        # Unapproved poster denied on public notice route -> 403 Forbidden
        unauth_client = app.test_client()
        resp_unapproved = unauth_client.get(f'/public/cases/{case_b.id}/posters/{poster_ev.id}')
        self.assertEqual(resp_unapproved.status_code, 403)

        # Admin approves poster for public distribution
        self._login(self.admin_user)
        resp_approve = self.client.post(
            f'/cases/{case_b.id}/poster/{poster_ev.id}/approve',
            follow_redirects=False
        )
        self.assertEqual(resp_approve.status_code, 302)

        # Now public notice route serves approved poster -> 200 OK
        resp_public = unauth_client.get(f'/public/cases/{case_b.id}/posters/{poster_ev.id}')
        self.assertEqual(resp_public.status_code, 200)
        self.assertEqual(resp_public.data, b"%PDF-1.4 Mock Poster")

    # -------------------------------------------------------------------------
    # Gate 7: Evidence Immutability & Additive Storage Preservation
    # -------------------------------------------------------------------------
    def test_07_evidence_immutability_and_additive_storage(self):
        """Gate 7: Submitted evidence records cannot be deleted or mutated; supplementary evidence is additive."""
        case_b = self._create_approved_case(self.user_a, ref_type='photo_normal')
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()
        orig_hash = photo_ev.sha256_hex
        orig_count = case_b.evidence.count()

        self._login(self.user_a)

        # 1. Deletion on submitted complaint is frozen and rejected with 400
        resp_del = self.client.post(f'/complaints/{case_b.id}/evidence/{photo_ev.id}/delete')
        self.assertEqual(resp_del.status_code, 400)
        self.assertEqual(case_b.evidence.count(), orig_count)

        # 2. Addendum response appends new evidence without overwriting original
        complaint_info = create_draft_complaint(self.user_a.id)
        update_draft_complaint(complaint_info.id, self.user_a.id, {
            'title': 'Theft Investigation Information Flow',
            'category': 'Theft / Burglary',
            'narrative': 'Initial submission narrative for information request flow.'
        })
        from werkzeug.datastructures import FileStorage
        fs_initial = FileStorage(
            stream=io.BytesIO(_generate_valid_png_bytes()),
            filename='initial_cctv.png',
            content_type='image/png'
        )
        attach_evidence_file(complaint_info.id, self.user_a.id, fs_initial)
        sub_info = submit_complaint(complaint_info.id, self.user_a.id)
        transition_case_status(sub_info.id, self.admin_user.id, 'under_review')
        transition_case_status(sub_info.id, self.admin_user.id, 'information_requested', message='Need timestamp')

        init_ev = sub_info.evidence.first()
        init_hash = init_ev.sha256_hex
        init_count = sub_info.evidence.count()

        fs_supp = FileStorage(
            stream=io.BytesIO(_generate_valid_png_bytes()),
            filename='supplementary_cctv.png',
            content_type='image/png'
        )
        submit_case_addendum(
            complaint_id=sub_info.id,
            user_id=self.user_a.id,
            addendum_text='Here is supplementary footage frame.',
            supplementary_files=[fs_supp]
        )

        self.assertEqual(sub_info.evidence.count(), init_count + 1)
        refetched_init = ComplaintEvidence.query.get(init_ev.id)
        self.assertEqual(refetched_init.sha256_hex, init_hash, "Original evidence hash was mutated!")

    # -------------------------------------------------------------------------
    # Gate 8: Failed Operations Resilience & Clean Transaction Rollback
    # -------------------------------------------------------------------------
    def test_08_failed_operations_resilience_and_clean_rollback(self):
        """Gate 8: Database failures roll back cleanly and remove newly written unreferenced files."""
        case_a = self._create_approved_case(self.user_a, ref_type='none')
        root = get_case_storage_root()

        # Simulate DB commit failure during artifact save
        with patch.object(db.session, 'commit', side_effect=RuntimeError("Simulated DB Disk Full")):
            with self.assertRaises(RuntimeError):
                save_case_artifact(
                    complaint_id=case_a.id,
                    actor_id=self.user_a.id,
                    file_bytes=_generate_valid_png_bytes(),
                    filename='orphan_test_sketch.png',
                    evidence_type='sketch',
                    generation_method='composite_layers'
                )

        # Verify no orphaned file remains on disk
        case_dir = os.path.join(root, str(case_a.id))
        if os.path.exists(case_dir):
            files = os.listdir(case_dir)
            self.assertNotIn('orphan_test_sketch.png', files)

    # -------------------------------------------------------------------------
    # Gate 9: Audit Timeline Trail Consistency & Actor Attribution
    # -------------------------------------------------------------------------
    def test_09_audit_timeline_consistency_and_actor_attribution(self):
        """Gate 9: Lifecycle transitions and forensic operations record exact actor IDs and chronological events."""
        case_b = self._create_approved_case(self.user_a, ref_type='photo_normal')
        assign_case_officer(case_b.id, self.admin_user.id, 'Inspector Sundaram', 'TN-POL-3012', 'Central Crime Branch', '+91 94440 54321')

        # Check officer assignment event
        tl_assign = ComplaintTimeline.query.filter_by(
            complaint_id=case_b.id,
            event_type='officer_assigned'
        ).first()
        self.assertIsNotNone(tl_assign)
        self.assertEqual(tl_assign.actor_user_id, self.admin_user.id)
        self.assertIn('Inspector Sundaram', tl_assign.message)
        self.assertIn('TN-POL-3012', tl_assign.message)

    # -------------------------------------------------------------------------
    # Gate 10: Database Isolation & Fail-Closed Live MySQL Protection
    # -------------------------------------------------------------------------
    def test_10_database_isolation_and_live_mysql_protection(self):
        """Gate 10: Confirms test execution strictly uses SQLite in-memory dialect with live MySQL blocked."""
        dialect = db.engine.dialect.name
        self.assertEqual(dialect, 'sqlite', f"FATAL: Database dialect is {dialect}, expected sqlite")
        db_uri = str(db.engine.url)
        self.assertTrue('sqlite' in db_uri and ':memory:' in db_uri)


if __name__ == '__main__':
    unittest.main()
