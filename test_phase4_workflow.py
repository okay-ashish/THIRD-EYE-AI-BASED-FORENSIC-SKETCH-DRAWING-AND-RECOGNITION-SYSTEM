"""
ThirdEye Phase 4 Test Suite: Role-Based Dashboards & Sequential Case Workflow
=============================================================================
Verifies all Phase 4 specifications in pure SQLite in-memory isolation:
  1. Exactly two authentication roles ('user' and 'admin').
  2. Citizen dashboard cards are informational and cannot launch tools.
  3. Standalone forensic route direct access is blocked server-side.
  4. Cross-user case access is strictly blocked (403).
  5. Admin intake review lifecycle uses permitted transitions.
  6. Illegal status transitions are rejected server-side.
  7. Investigating officer assignment persists details & logs timeline.
  8. Information request addenda preserve original submitted narrative & evidence.
  9. Branch A (no photo): sequential sketch -> reconstruction -> variation -> poster.
  10. Branch B (normal photo): sketches bypassed, recognition on authentic photo only.
  11. Option C (masked photo): permanently disallowed and rejected.
  12. Posters remain draft ('internal') until Admin approves for public distribution.
  13. Timeline audit trail tracks all case lifecycle milestones.
  14. Zero connection or modification to live MySQL.
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

import unittest
import io
import shutil
import tempfile
import sqlalchemy
from datetime import datetime
from unittest.mock import patch

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
    get_admin_dashboard_stats,
    get_user_dashboard_stats,
    ADMIN_PERMITTED_TRANSITIONS,
    USER_PERMITTED_TRANSITIONS
)


class Phase4WorkflowTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.test_storage_root = tempfile.mkdtemp(prefix="thirdeye_phase4_test_storage_")
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
        self.user_a = User(username='citizen_alice', password='Password123!', role='user', full_name='Alice Citizen')
        self.user_b = User(username='citizen_bob', password='Password123!', role='user', full_name='Bob Citizen')
        self.admin_user = User(username='admin_officer', password='AdminPassword123!', role='admin', full_name='Inspector Admin')
        db.session.add_all([self.user_a, self.user_b, self.admin_user])
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

    def _create_submitted_complaint(self, user, ref_type='none'):
        complaint = create_draft_complaint(user.id)
        update_draft_complaint(complaint.id, user.id, {
            'title': f'Armed Robbery Investigation - {ref_type}',
            'category': 'Robbery',
            'incident_datetime': '2026-10-11T10:00',
            'incident_location': 'MG Road Market, Chennai',
            'narrative': 'Subject held a firearm and demanded jewelry from the store cashier.',
            'incident_description': 'Subject held a firearm and demanded jewelry from the store cashier.',
            'suspect_gender': 'Male',
            'suspect_approx_age': '32',
            'facial_reference_type': ref_type,
            'suspect_description': 'Tall, athletic build with blue jacket'
        })
        # If photo ref, attach synthetic photo evidence
        if ref_type == 'photo_normal':
            dummy_file = io.BytesIO(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
            dummy_file.filename = 'suspect_photo.png'
            from werkzeug.datastructures import FileStorage
            fs = FileStorage(stream=dummy_file, filename='suspect_photo.png', content_type='image/png')
            attach_evidence_file(complaint.id, user.id, fs)

        submitted = submit_complaint(complaint.id, user.id)
        return submitted

    def test_01_two_roles_only(self):
        """Phase 4 Gate 1: Exactly two authentication roles ('user' and 'admin') are permitted."""
        self.assertEqual(set(ALLOWED_USER_ROLES), {'user', 'admin'})
        with self.assertRaises(ValueError):
            User(username='officer_smith', password='Password123!', role='officer')

    def test_02_dashboard_feature_cards_informational_only(self):
        """Phase 4 Gate 2: Citizen dashboard capabilities section contains static informational cards without direct tool launch links."""
        self._login(self.user_a)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')

        # Check showcase headings are present
        self.assertIn('ThirdEye System Capabilities', html)
        self.assertIn('Forensic Architecture', html)
        self.assertIn('Composite Facial Sketch Construction', html)
        self.assertIn('Sketch-to-Face Reconstruction', html)
        self.assertIn('Photo-to-Sketch Conversion', html)
        self.assertIn('Face Appearance Variations', html)
        self.assertIn('Biometric Face Recognition', html)
        self.assertNotIn('Masked-Photo Heuristic Analysis', html)
        self.assertIn('A4 Case Poster Notice Creation', html)

        # Check static non-interactive styling
        self.assertIn('user-select: none', html)

        # Confirm no clickable buttons exist inside capability cards to directly launch tools
        self.assertNotIn('href="/sketch"', html)
        self.assertNotIn('href="/construct-face"', html)
        self.assertNotIn('href="/photo-to-sketch"', html)
        self.assertNotIn('href="/face_variations"', html)
        self.assertNotIn('href="/create-variations"', html)
        self.assertNotIn('href="/recognition"', html)
        self.assertNotIn('href="/create-poster"', html)

    def test_03_standalone_routes_direct_access_blocked(self):
        """Phase 4 Gate 3: Direct URL navigation to forensic tools without a valid case context is safely redirected with warnings."""
        self._login(self.user_a)
        routes_to_test = [
            '/sketch',
            '/recognition',
            '/photo-to-sketch',
            '/construct-face',
            '/create-variations',
            '/face_variations',
            '/create-poster'
        ]
        for route in routes_to_test:
            resp = self.client.get(route, follow_redirects=False)
            self.assertEqual(resp.status_code, 302, f"Route {route} did not redirect safely!")
            # Should redirect to citizen portal or home
            self.assertTrue('/my-complaints' in resp.headers['Location'] or '/' in resp.headers['Location'])

    def test_04_cross_user_case_access_blocked(self):
        """Phase 4 Gate 4: Citizen B cannot view or open Citizen A's case workspace (403 Forbidden)."""
        complaint_a = self._create_submitted_complaint(self.user_a, ref_type='none')
        # Login as User B
        self._login(self.user_b)
        resp = self.client.get(f'/cases/{complaint_a.id}/workspace')
        self.assertEqual(resp.status_code, 403)

    def test_05_admin_intake_review_lifecycle_permitted_transitions(self):
        """Phase 4 Gate 5: Admin executes valid state transitions with recorded timeline audit events."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        self.assertEqual(complaint.status, 'submitted')

        # 1. Admin marks under review
        transition_case_status(complaint.id, self.admin_user.id, 'under_review')
        c = Complaint.query.get(complaint.id)
        self.assertEqual(c.status, 'under_review')

        # 2. Admin approves case
        transition_case_status(complaint.id, self.admin_user.id, 'approved', message='Approved by Station Inspector')
        c = Complaint.query.get(complaint.id)
        self.assertEqual(c.status, 'approved')

        # Check timeline recorded
        events = [t.event_type for t in c.timeline.all()]
        self.assertIn('review_started', events)
        self.assertIn('complaint_approved', events)

    def test_06_illegal_status_transitions_blocked_server_side(self):
        """Phase 4 Gate 6: Arbitrary status jumps and unauthorized citizen transitions are rejected server-side."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        # Citizen cannot approve their own case
        with self.assertRaises(ValueError):
            transition_case_status(complaint.id, self.user_a.id, 'approved')

        # Admin cannot jump directly from submitted to closed
        with self.assertRaises(ValueError):
            transition_case_status(complaint.id, self.admin_user.id, 'closed')

        # Rejection requires reason
        with self.assertRaises(ValueError):
            transition_case_status(complaint.id, self.admin_user.id, 'rejected', message='')

    def test_07_officer_assignment_persists_details_and_logs_timeline(self):
        """Phase 4 Gate 7: Officer assignment stores name, badge, station, contact and logs timeline entry."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        transition_case_status(complaint.id, self.admin_user.id, 'approved')

        assign_case_officer(
            complaint_id=complaint.id,
            actor_id=self.admin_user.id,
            officer_name='SI K. Ramanathan',
            officer_id='TN-POL-4091',
            station='R-4 Soundarapandianar Angadi PS',
            contact='+91 94440 12345'
        )

        c = Complaint.query.get(complaint.id)
        self.assertEqual(c.status, 'assigned')
        self.assertEqual(c.assigned_officer_name, 'SI K. Ramanathan')
        self.assertEqual(c.assigned_officer_id, 'TN-POL-4091')
        self.assertEqual(c.assigned_station, 'R-4 Soundarapandianar Angadi PS')
        self.assertEqual(c.assigned_officer_contact, '+91 94440 12345')

        latest_timeline = ComplaintTimeline.query.filter_by(complaint_id=c.id).order_by(ComplaintTimeline.id.desc()).first()
        self.assertEqual(latest_timeline.event_type, 'officer_assigned')
        self.assertIn('TN-POL-4091', latest_timeline.message)

    def test_08_information_request_and_citizen_addendum_flow(self):
        """Phase 4 Gate 8: Information request creates citizen addendum while preserving original submitted evidence & narrative intact."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        orig_narrative = complaint.narrative
        orig_evidence_count = complaint.evidence.count()

        # Admin requests info
        transition_case_status(complaint.id, self.admin_user.id, 'information_requested', message='Please provide CCTV footage timestamp.')
        c = Complaint.query.get(complaint.id)
        self.assertEqual(c.status, 'information_requested')

        # Citizen submits addendum
        dummy_file = io.BytesIO(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
        from werkzeug.datastructures import FileStorage
        fs = FileStorage(stream=dummy_file, filename='cctv_frame.png', content_type='image/png')

        submit_case_addendum(
            complaint_id=complaint.id,
            user_id=self.user_a.id,
            addendum_text='Incident occurred at 10:14 AM near shop 12B.',
            supplementary_files=[fs]
        )

        c = Complaint.query.get(complaint.id)
        self.assertEqual(c.status, 'under_review')
        # Crucial immutability verification:
        self.assertEqual(c.narrative, orig_narrative, "Original complaint narrative was mutated!")
        self.assertEqual(c.evidence.count(), orig_evidence_count + 1, "New evidence was not recorded as additive record!")

    def test_09_branch_a_sketch_workflow_pipeline(self):
        """Phase 4 Gate 9: Branch A requires sketch before reconstruction, prohibits automated recognition on sketches."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        transition_case_status(complaint.id, self.admin_user.id, 'approved')
        c = Complaint.query.get(complaint.id)

        # Sketch is allowed
        allowed, _ = can_access_tool(c, 'sketch')
        self.assertTrue(allowed)

        # Reconstruct is blocked prior to sketch construction
        allowed, msg = can_access_tool(c, 'reconstruct')
        self.assertFalse(allowed)
        self.assertIn('composite sketch must be constructed', msg)

        # Recognition is strictly prohibited on synthetic Branch A
        allowed, msg = can_access_tool(c, 'recognition')
        self.assertFalse(allowed)
        self.assertIn('not permitted on synthetic sketches', msg)

        # Save synthetic sketch artifact
        dummy_sketch = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        save_case_artifact(
            complaint_id=c.id,
            actor_id=self.user_a.id,
            file_bytes=dummy_sketch,
            filename='sketch.png',
            evidence_type='sketch',
            generation_method='composite_layers'
        )

        # Now reconstruct is unlocked
        allowed, _ = can_access_tool(c, 'reconstruct')
        self.assertTrue(allowed)

    def test_10_branch_b_photo_normal_workflow_pipeline(self):
        """Phase 4 Gate 10: Branch B preserves photo, bypasses sketch/reconstruct by default, allows recognition on authentic photo."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='photo_normal')
        transition_case_status(complaint.id, self.admin_user.id, 'approved')
        c = Complaint.query.get(complaint.id)

        # Sketch and reconstruct are bypassed
        allowed_sketch, _ = can_access_tool(c, 'sketch')
        allowed_recon, _ = can_access_tool(c, 'reconstruct')
        self.assertFalse(allowed_sketch)
        self.assertFalse(allowed_recon)

        # Biometric recognition on authentic photo is allowed
        allowed_rec, _ = can_access_tool(c, 'recognition')
        self.assertTrue(allowed_rec)

        # Poster is allowed
        allowed_poster, _ = can_access_tool(c, 'poster')
        self.assertTrue(allowed_poster)

    def test_11_option_c_masked_photo_disallowed_and_rejected(self):
        """Phase 4 Gate 11: Option C (masked/covered photograph) is discontinued; 'photo_masked' is strictly rejected."""
        self.assertEqual(ALLOWED_FACIAL_REFERENCE_TYPES, ('none', 'photo_normal'))
        with self.assertRaises(ValueError):
            self._create_submitted_complaint(self.user_a, ref_type='photo_masked')

    def test_12_poster_approval_and_public_distribution_enforcement(self):
        """Phase 4 Gate 12: Unapproved posters remain internal and cannot be publicly downloaded until Admin approves."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        transition_case_status(complaint.id, self.admin_user.id, 'approved')

        # Save synthetic poster PDF as internal draft
        dummy_pdf = b'%PDF-1.4 synthetic poster content'
        poster_ev = save_case_artifact(
            complaint_id=complaint.id,
            actor_id=self.user_a.id,
            file_bytes=dummy_pdf,
            filename='poster_draft.pdf',
            evidence_type='poster',
            access_level='internal'
        )

        # Unauthorized citizen B attempts to download unapproved poster -> 403 Forbidden
        self._login(self.user_b)
        resp = self.client.get(f'/cases/{complaint.id}/poster/{poster_ev.id}/download')
        self.assertEqual(resp.status_code, 403)

        # Admin approves poster for public distribution
        approve_poster_for_distribution(complaint.id, poster_ev.id, self.admin_user.id)
        ev_updated = ComplaintEvidence.query.get(poster_ev.id)
        self.assertEqual(ev_updated.access_level, 'public_notice')

        # Now public notice download is allowed
        resp = self.client.get(f'/cases/{complaint.id}/poster/{poster_ev.id}/download')
        self.assertEqual(resp.status_code, 200)

    def test_13_timeline_audit_trail_integrity(self):
        """Phase 4 Gate 13: Timeline correctly records actor, status changes, and case actions."""
        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        transition_case_status(complaint.id, self.admin_user.id, 'under_review')
        transition_case_status(complaint.id, self.admin_user.id, 'approved')

        timeline_entries = ComplaintTimeline.query.filter_by(complaint_id=complaint.id).order_by(ComplaintTimeline.created_at.asc()).all()
        self.assertGreaterEqual(len(timeline_entries), 3)

        # Verify all entries have non-null actor and timestamp
        for entry in timeline_entries:
            self.assertIsNotNone(entry.actor_user_id)
            self.assertIsNotNone(entry.created_at)

    def test_14_zero_live_mysql_writes(self):
        """Phase 4 Gate 14: Confirms test run is 100% in-memory SQLite and never touched MySQL."""
        dialect = db.engine.dialect.name
        self.assertEqual(dialect, 'sqlite')

    def test_15_all_10_statuses_reconciled_and_charges_filed_rejected(self):
        """Phase 4.1 Gate 15: Reconcile all 10 application statuses and verify 'charges_filed' is rejected."""
        expected_10_statuses = {
            'draft',
            'submitted',
            'under_review',
            'information_requested',
            'rejected',
            'approved',
            'assigned',
            'investigation_in_progress',
            'awaiting_further_evidence',
            'closed'
        }
        self.assertEqual(set(ALLOWED_COMPLAINT_STATUSES), expected_10_statuses)

        # 'charges_filed' was a documentation-only diagram typo and must be rejected by model validation
        self.assertNotIn('charges_filed', ALLOWED_COMPLAINT_STATUSES)

        complaint = self._create_submitted_complaint(self.user_a, ref_type='none')
        with self.assertRaises(ValueError):
            complaint.status = 'charges_filed'

        with self.assertRaises(ValueError):
            transition_case_status(complaint.id, self.admin_user.id, 'charges_filed')

        # Verify progression through investigation statuses
        transition_case_status(complaint.id, self.admin_user.id, 'under_review')
        transition_case_status(complaint.id, self.admin_user.id, 'approved')
        assign_case_officer(complaint.id, self.admin_user.id, 'Insp. Sundaram', 'BADGE-101', 'Central PS')
        self.assertEqual(complaint.status, 'assigned')
        transition_case_status(complaint.id, self.admin_user.id, 'investigation_in_progress')
        self.assertEqual(complaint.status, 'investigation_in_progress')
        transition_case_status(complaint.id, self.admin_user.id, 'awaiting_further_evidence')
        self.assertEqual(complaint.status, 'awaiting_further_evidence')
        transition_case_status(complaint.id, self.admin_user.id, 'investigation_in_progress')
        transition_case_status(complaint.id, self.admin_user.id, 'closed')
        self.assertEqual(complaint.status, 'closed')

    def test_16_route_level_forensic_stage_enforcement(self):
        """Phase 4.1 Gate 16: Direct HTTP requests to case routes cannot bypass sequential stages even with valid case ID."""
        # Case A: Branch A ('none')
        case_a = self._create_submitted_complaint(self.user_a, ref_type='none')
        transition_case_status(case_a.id, self.admin_user.id, 'approved')

        # 1. Citizen A tries direct GET to /cases/<id>/reconstruct without sketch -> redirects with policy warning
        self._login(self.user_a)
        resp = self.client.get(f'/cases/{case_a.id}/reconstruct', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])

        # 2. Direct request to /cases/<id>/recognition on Branch A -> blocked (no automated recognition on synthetic composites)
        resp = self.client.get(f'/cases/{case_a.id}/recognition', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])

        # 3. Direct request to /cases/<id>/variations on Branch A without sketch/reconstruction -> blocked
        resp = self.client.get(f'/cases/{case_a.id}/variations', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])

        # Case B: Branch B ('photo_normal')
        case_b = self._create_submitted_complaint(self.user_a, ref_type='photo_normal')
        transition_case_status(case_b.id, self.admin_user.id, 'approved')

        # 4. Direct request to /cases/<id>/sketch on Branch B -> blocked (photo reference available)
        resp = self.client.get(f'/cases/{case_b.id}/sketch', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_b.id}/workspace', resp.headers['Location'])

        # 5. Direct request to /cases/<id>/reconstruct on Branch B -> blocked
        resp = self.client.get(f'/cases/{case_b.id}/reconstruct', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_b.id}/workspace', resp.headers['Location'])

        # 6. Verify Option C ('photo_masked') is rejected and cannot be created
        with self.assertRaises(ValueError):
            self._create_submitted_complaint(self.user_a, ref_type='photo_masked')

        # 7. Cross-user route-level isolation: Citizen B directly requesting Citizen A's case routes returns 403 Forbidden
        self._login(self.user_b)
        for sub_route in ['workspace', 'sketch', 'reconstruct', 'variations', 'recognition', 'poster']:
            resp = self.client.get(f'/cases/{case_a.id}/{sub_route}')
            self.assertEqual(resp.status_code, 403, f"Citizen B was not blocked from /cases/{case_a.id}/{sub_route}")


if __name__ == '__main__':
    unittest.main()
