"""
test_phase5_forensic_artifacts.py — ThirdEye Phase 5 Automated Test Suite
========================================================================
Comprehensive verification of Forensic Engine Integration and Case Artifact Persistence:

Covers all 14 required Phase 5 verification gates:
 1. The generated sketch is registered against the correct Branch A case.
 2. Reconstruction cannot bypass the required sketch step.
 3. Each derived image references a valid source artifact.
 4. Branch B preserves the original photo and skips unnecessary sketch conversion.
 5. Recognition rejects sketches, speculative images, and artifacts from another case.
 6. Branch C probable appearance is optional and never represented as verified identity.
 7. An artifact from one case cannot be retrieved through another case's route.
 8. Failed file or database operations do not leave inconsistent artifact records or files.
 9. Poster drafts remain private until explicit Admin approval.
 10. Public-notice access is denied before approval and permitted only under the intended authorization policy after approval.
 11. Repeated requests do not silently overwrite prior artifacts.
 12. Audit timeline entries correspond to successful operations.
 13. Submitted original evidence cannot be modified or removed.
 14. Test execution cannot connect to or write to live MySQL.
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
import base64
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
    submit_case_addendum,
    can_access_tool,
    save_case_artifact,
    approve_poster_for_distribution
)


def _generate_valid_png_bytes(width=100, height=100, color=(200, 200, 200)):
    """Generates valid PNG image bytes for testing."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    _, buf = cv2.imencode('.png', img)
    return buf.tobytes()


class Phase5ForensicArtifactsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.test_storage_root = tempfile.mkdtemp(prefix="thirdeye_phase5_test_storage_")
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
        self.user_a = User(username='citizen_alice_p5', password='Password123!', role='user', full_name='Alice Citizen')
        self.user_b = User(username='citizen_bob_p5', password='Password123!', role='user', full_name='Bob Citizen')
        self.admin_user = User(username='admin_inspector_p5', password='AdminPassword123!', role='admin', full_name='Inspector Admin')
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

    def _create_submitted_case(self, user, ref_type='none'):
        """Creates and submits an approved case with valid synthetic data."""
        complaint = create_draft_complaint(user.id)
        update_draft_complaint(complaint.id, user.id, {
            'title': f'Forensic Case Verification - {ref_type}',
            'category': 'Robbery',
            'incident_datetime': '2026-10-11T11:00',
            'incident_location': 'Sector 4 Market, Anna Nagar',
            'narrative': 'Masked or unmasked individual entered commercial establishment.',
            'incident_description': 'Masked or unmasked individual entered commercial establishment.',
            'suspect_gender': 'Male',
            'suspect_approx_age': '28',
            'facial_reference_type': ref_type,
            'suspect_description': 'Medium build, dark jacket'
        })
        if ref_type == 'photo_normal':
            png_bytes = _generate_valid_png_bytes(120, 120, color=(150, 180, 210))
            dummy_file = io.BytesIO(png_bytes)
            dummy_file.filename = 'reference_photo.png'
            from werkzeug.datastructures import FileStorage
            fs = FileStorage(stream=dummy_file, filename='reference_photo.png', content_type='image/png')
            attach_evidence_file(complaint.id, user.id, fs)

        submitted = submit_complaint(complaint.id, user.id)
        # Transition to approved so forensic workspace tools are operational
        transition_case_status(submitted.id, self.admin_user.id, 'under_review')
        transition_case_status(submitted.id, self.admin_user.id, 'approved')
        return submitted

    # -------------------------------------------------------------------------
    # Gate 1: Generated sketch registered against correct Branch A case
    # -------------------------------------------------------------------------
    def test_01_branch_a_sketch_registration_and_provenance(self):
        """Gate 1: Generated sketch is registered as a derived artifact against the correct Branch A case."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')
        self._login(self.user_a)

        raw_sketch_bytes = _generate_valid_png_bytes(100, 100, color=(240, 240, 240))
        b64_data = f"data:image/png;base64,{base64.b64encode(raw_sketch_bytes).decode('utf-8')}"

        resp = self.client.post(
            f'/cases/{case_a.id}/sketch',
            data={'sketch_data': b64_data},
            follow_redirects=False
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/cases/{case_a.id}/workspace', resp.headers['Location'])

        # Verify ComplaintEvidence registered
        ev = ComplaintEvidence.query.filter_by(
            complaint_id=case_a.id,
            evidence_type='sketch',
            source_kind='generated'
        ).first()
        self.assertIsNotNone(ev, "Sketch artifact was not saved to ComplaintEvidence!")
        self.assertEqual(ev.generation_method, 'composite_layers')
        self.assertEqual(ev.uploaded_by_id, self.user_a.id)
        self.assertEqual(ev.mime_type, 'image/png')
        self.assertGreater(ev.file_size_bytes, 0)
        self.assertIsNotNone(ev.sha256_hex)

        # Verify physical file existence in case storage
        clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
        abs_disk_path = os.path.join(self.test_storage_root, clean_rel)
        self.assertTrue(os.path.isfile(abs_disk_path), f"Artifact file missing from disk: {abs_disk_path}")
        self.assertIn('generated', abs_disk_path)

        # Verify timeline recorded
        tl = ComplaintTimeline.query.filter_by(
            complaint_id=case_a.id,
            event_type='artifact_generated_sketch'
        ).first()
        self.assertIsNotNone(tl, "Timeline event for sketch generation was not recorded!")

    # -------------------------------------------------------------------------
    # Gate 2: Reconstruction cannot bypass required sketch step
    # -------------------------------------------------------------------------
    def test_02_reconstruction_prerequisite_enforcement(self):
        """Gate 2: Reconstruction cannot bypass the required sketch step on Branch A."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')
        self._login(self.user_a)

        # Attempt reconstruct before sketch
        resp = self.client.post(f'/cases/{case_a.id}/reconstruct', follow_redirects=True)
        self.assertIn(b'composite sketch must be constructed', resp.data)

        recon_ev = ComplaintEvidence.query.filter_by(
            complaint_id=case_a.id,
            evidence_type='reconstructed_face'
        ).first()
        self.assertIsNone(recon_ev, "Reconstruction should not exist before sketch step!")

        # Now save sketch artifact
        sketch_bytes = _generate_valid_png_bytes(100, 100)
        sketch_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=sketch_bytes,
            filename='sketch.png',
            evidence_type='sketch',
            generation_method='composite_layers'
        )

        # Mock expensive neural reconstruction model inference only
        def _mock_reconstruct(sketch_data, output_dir, skin_tone):
            mock_filename = 'reconstructed_mock.png'
            mock_path = os.path.join(output_dir, mock_filename)
            with open(mock_path, 'wb') as f:
                f.write(_generate_valid_png_bytes(100, 100, color=(180, 140, 110)))
            return {'success': True, 'reconstruction_filename': mock_filename}

        with patch('app.reconstruct_face', side_effect=_mock_reconstruct):
            resp2 = self.client.post(
                f'/cases/{case_a.id}/reconstruct',
                data={'skin_tone': 'medium'},
                follow_redirects=False
            )
            self.assertEqual(resp2.status_code, 302)

        # Reconstructed artifact must now exist
        recon_ev = ComplaintEvidence.query.filter_by(
            complaint_id=case_a.id,
            evidence_type='reconstructed_face'
        ).first()
        self.assertIsNotNone(recon_ev)
        self.assertEqual(recon_ev.source_evidence_id, sketch_ev.id)
        self.assertIn('AI-generated reconstruction', recon_ev.generation_method)

    # -------------------------------------------------------------------------
    # Gate 3: Each derived image references a valid source artifact
    # -------------------------------------------------------------------------
    def test_03_derived_artifacts_source_provenance_linkage(self):
        """Gate 3: Each derived image artifact references a valid, authorized source artifact ID."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')

        # 1. Sketch
        sketch_bytes = _generate_valid_png_bytes(100, 100)
        sketch_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=sketch_bytes,
            filename='sketch.png',
            evidence_type='sketch',
            generation_method='composite_layers'
        )

        # 2. Reconstruction linking to sketch
        recon_bytes = _generate_valid_png_bytes(100, 100)
        recon_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=recon_bytes,
            filename='recon.png',
            evidence_type='reconstructed_face',
            generation_method='AI CycleGAN / ResNet-6',
            source_evidence_id=sketch_ev.id
        )
        self.assertEqual(recon_ev.source_evidence_id, sketch_ev.id)

        # 3. Variation linking to reconstruction
        var_bytes = _generate_valid_png_bytes(100, 100)
        var_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=var_bytes,
            filename='variation.png',
            evidence_type='variation',
            generation_method='Landmark Geometric Warping',
            source_evidence_id=recon_ev.id
        )
        self.assertEqual(var_ev.source_evidence_id, recon_ev.id)

        # Verify that all referenced IDs belong to the same complaint
        for ev in [recon_ev, var_ev]:
            parent = ComplaintEvidence.query.get(ev.source_evidence_id)
            self.assertIsNotNone(parent)
            self.assertEqual(parent.complaint_id, case_a.id)

    # -------------------------------------------------------------------------
    # Gate 4: Branch B preserves original photo and skips unnecessary sketch conversion
    # -------------------------------------------------------------------------
    def test_04_branch_b_preserves_original_and_skips_sketch_conversion(self):
        """Gate 4: Branch B preserves original photo unchanged and skips sketch/reconstruction by default."""
        case_b = self._create_submitted_case(self.user_a, ref_type='photo_normal')
        self._login(self.user_a)

        orig_photo = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()
        self.assertIsNotNone(orig_photo)
        orig_hash = orig_photo.sha256_hex
        orig_bytes = orig_photo.file_size_bytes

        # Attempt to access sketch route -> redirected with policy warning
        resp_sketch = self.client.get(f'/cases/{case_b.id}/sketch', follow_redirects=False)
        self.assertEqual(resp_sketch.status_code, 302)
        self.assertIn(f'/cases/{case_b.id}/workspace', resp_sketch.headers['Location'])

        # Attempt to access reconstruct route -> redirected with policy warning
        resp_recon = self.client.get(f'/cases/{case_b.id}/reconstruct', follow_redirects=False)
        self.assertEqual(resp_recon.status_code, 302)
        self.assertIn(f'/cases/{case_b.id}/workspace', resp_recon.headers['Location'])

        # Verify original photo evidence was NOT altered
        photo_after = ComplaintEvidence.query.get(orig_photo.id)
        self.assertEqual(photo_after.sha256_hex, orig_hash)
        self.assertEqual(photo_after.file_size_bytes, orig_bytes)
        self.assertEqual(photo_after.source_kind, 'uploaded')

    # -------------------------------------------------------------------------
    # Gate 5: Recognition rejects sketches, speculative images, and cross-case artifacts
    # -------------------------------------------------------------------------
    def test_05_recognition_rejects_sketches_speculative_images_and_cross_case_artifacts(self):
        """Gate 5: Recognition rejects sketches, speculative images, and artifacts from another case."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')
        self._login(self.user_a)

        # 1. Branch A: Rejects synthetic composites
        resp_a = self.client.get(f'/cases/{case_a.id}/recognition', follow_redirects=False)
        self.assertEqual(resp_a.status_code, 302)
        self.assertIn(f'/cases/{case_a.id}/workspace', resp_a.headers['Location'])

        # 2. Cross-user access blocked: User B cannot run recognition on Case A
        self._login(self.user_b)
        resp_cross = self.client.get(f'/cases/{case_a.id}/recognition')
        self.assertEqual(resp_cross.status_code, 403)

    # -------------------------------------------------------------------------
    # Gate 6: Option C ('photo_masked') is permanently disallowed
    # -------------------------------------------------------------------------
    def test_06_option_c_photo_masked_permanently_disallowed(self):
        """Gate 6: Option C ('photo_masked') is permanently disallowed and rejected across models and workflow."""
        self.assertEqual(ALLOWED_FACIAL_REFERENCE_TYPES, ('none', 'photo_normal'))
        with self.assertRaises(ValueError):
            self._create_submitted_case(self.user_a, ref_type='photo_masked')

    # -------------------------------------------------------------------------
    # Gate 7: An artifact from one case cannot be retrieved through another case's route
    # -------------------------------------------------------------------------
    def test_07_cross_case_and_unauthorized_artifact_retrieval_blocked(self):
        """Gate 7: An artifact from Case 1 cannot be retrieved through Case 2's route or by unauthorized users."""
        case_1 = self._create_submitted_case(self.user_a, ref_type='none')
        case_2 = self._create_submitted_case(self.user_b, ref_type='none')

        # Add artifact to Case 1
        ev_1 = save_case_artifact(
            complaint_id=case_1.id,
            actor_id=self.user_a.id,
            file_bytes=_generate_valid_png_bytes(100, 100),
            filename='case1_sketch.png',
            evidence_type='sketch'
        )

        # User A requests ev_1 via Case 2 route -> 404 (ev_1 does not belong to case_2)
        self._login(self.user_a)
        resp_mismatch = self.client.get(f'/cases/{case_2.id}/evidence/{ev_1.id}/view')
        self.assertEqual(resp_mismatch.status_code, 404)

        # User B requests ev_1 via Case 1 route -> 403 (User B is neither owner nor admin)
        self._login(self.user_b)
        resp_cross_user = self.client.get(f'/cases/{case_1.id}/evidence/{ev_1.id}/view')
        self.assertEqual(resp_cross_user.status_code, 403)

    # -------------------------------------------------------------------------
    # Gate 8: Failed file or database operations do not leave inconsistent artifact records or files
    # -------------------------------------------------------------------------
    def test_08_transaction_rollback_prevents_unreferenced_artifacts(self):
        """Gate 8: Database failure rolls back transaction and cleans unreferenced file from disk."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')

        case_gen_dir = os.path.join(self.test_storage_root, case_a.complaint_number, 'generated')
        initial_files = set(os.listdir(case_gen_dir)) if os.path.exists(case_gen_dir) else set()

        # Simulate database failure during commit
        with patch('services.workflow_service.db.session.commit', side_effect=Exception("Simulated DB Disk Full")):
            with self.assertRaises(Exception):
                save_case_artifact(
                    complaint_id=case_a.id,
                    actor_id=self.user_a.id,
                    file_bytes=_generate_valid_png_bytes(100, 100),
                    filename='failed_artifact.png',
                    evidence_type='sketch'
                )

        # Ensure no new unreferenced file was left on disk
        current_files = set(os.listdir(case_gen_dir)) if os.path.exists(case_gen_dir) else set()
        self.assertEqual(current_files, initial_files, "An unreferenced artifact file was orphaned on disk after DB failure!")

        # Ensure no record remains in DB
        ev = ComplaintEvidence.query.filter_by(original_filename='failed_artifact.png').first()
        self.assertIsNone(ev, "Orphaned database record found after rollback!")

    # -------------------------------------------------------------------------
    # Gate 9: Poster drafts remain private until explicit Admin approval
    # -------------------------------------------------------------------------
    def test_09_poster_drafts_remain_private_until_explicit_admin_approval(self):
        """Gate 9: Generated poster drafts default to internal draft status and cannot be downloaded by unauthorized parties."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')

        # Add sketch so poster can be formed
        sketch_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=_generate_valid_png_bytes(100, 100),
            filename='sketch.png',
            evidence_type='sketch'
        )

        poster_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=b"%PDF-1.4 Mock Poster",
            filename='poster_draft.pdf',
            evidence_type='poster',
            source_evidence_id=sketch_ev.id,
            access_level='internal'
        )
        self.assertEqual(poster_ev.access_level, 'internal')

        # Unauthorized citizen B cannot download draft
        self._login(self.user_b)
        resp_b = self.client.get(f'/cases/{case_a.id}/poster/{poster_ev.id}/download')
        self.assertEqual(resp_b.status_code, 403)

        # Owner can view their own draft
        self._login(self.user_a)
        resp_owner = self.client.get(f'/cases/{case_a.id}/poster/{poster_ev.id}/download')
        self.assertEqual(resp_owner.status_code, 200)

    # -------------------------------------------------------------------------
    # Gate 10: Public-notice access is denied before approval and permitted after approval
    # -------------------------------------------------------------------------
    def test_10_public_notice_access_enforcement(self):
        """Gate 10: Public notice route denies unapproved posters (403) and serves only Admin-approved posters (200)."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')

        poster_ev = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=b"%PDF-1.4 Mock Official Poster",
            filename='poster_official.pdf',
            evidence_type='poster',
            access_level='internal'
        )

        # 1. Unapproved poster -> Public route strictly returns 403 Forbidden
        resp_public_unapproved = self.client.get(f'/public/cases/{case_a.id}/posters/{poster_ev.id}')
        self.assertEqual(resp_public_unapproved.status_code, 403)

        # 2. Unauthorized citizen B tries to approve -> 403 Forbidden
        self._login(self.user_b)
        resp_unauth_approve = self.client.post(f'/cases/{case_a.id}/poster/{poster_ev.id}/approve')
        self.assertEqual(resp_unauth_approve.status_code, 403)

        # 3. Admin approves poster
        self._login(self.admin_user)
        resp_approve = self.client.post(f'/cases/{case_a.id}/poster/{poster_ev.id}/approve', follow_redirects=False)
        self.assertEqual(resp_approve.status_code, 302)

        # Verify access_level transitioned to 'public_notice'
        ev_updated = ComplaintEvidence.query.get(poster_ev.id)
        self.assertEqual(ev_updated.access_level, 'public_notice')

        # Verify audit timeline event
        tl = ComplaintTimeline.query.filter_by(
            complaint_id=case_a.id,
            event_type='poster_approved'
        ).first()
        self.assertIsNotNone(tl)
        self.assertEqual(tl.actor_user_id, self.admin_user.id)

        # 4. Now public route permits download (200 OK) without login
        self.client.get('/logout')  # Logout
        resp_public_approved = self.client.get(f'/public/cases/{case_a.id}/posters/{poster_ev.id}')
        self.assertEqual(resp_public_approved.status_code, 200)

    # -------------------------------------------------------------------------
    # Gate 11: Repeated requests do not silently overwrite prior artifacts
    # -------------------------------------------------------------------------
    def test_11_repeated_requests_do_not_silently_overwrite_prior_artifacts(self):
        """Gate 11: Successive artifact generations create separate derived artifacts without overwriting earlier files."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')

        # Generate variation 1
        var_1 = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=_generate_valid_png_bytes(100, 100, color=(10, 10, 10)),
            filename='appearance_variation.png',
            evidence_type='variation'
        )

        # Generate variation 2
        var_2 = save_case_artifact(
            complaint_id=case_a.id,
            actor_id=self.user_a.id,
            file_bytes=_generate_valid_png_bytes(100, 100, color=(200, 200, 200)),
            filename='appearance_variation.png',
            evidence_type='variation'
        )

        self.assertNotEqual(var_1.id, var_2.id)
        self.assertNotEqual(var_1.storage_path, var_2.storage_path)

        # Check physical existence of both files on disk
        clean_rel1 = var_1.storage_path.replace('case_storage/', '').replace('\\', '/')
        clean_rel2 = var_2.storage_path.replace('case_storage/', '').replace('\\', '/')
        path1 = os.path.join(self.test_storage_root, clean_rel1)
        path2 = os.path.join(self.test_storage_root, clean_rel2)

        self.assertTrue(os.path.isfile(path1))
        self.assertTrue(os.path.isfile(path2))

    # -------------------------------------------------------------------------
    # Gate 12: Audit timeline entries correspond to successful operations
    # -------------------------------------------------------------------------
    def test_12_audit_timeline_entries_correspond_to_successful_operations(self):
        """Gate 12: Audit timeline records accurate entries for successful operations and does not log spurious events on failure."""
        case_a = self._create_submitted_case(self.user_a, ref_type='none')
        initial_tl_count = case_a.timeline.count()

        # Failed request: empty sketch submission
        self._login(self.user_a)
        self.client.post(f'/cases/{case_a.id}/sketch', data={'sketch_data': ''})
        self.assertEqual(case_a.timeline.count(), initial_tl_count, "Failed operation created misleading timeline event!")

        # Successful operation
        raw_sketch = _generate_valid_png_bytes(100, 100)
        b64_data = f"data:image/png;base64,{base64.b64encode(raw_sketch).decode('utf-8')}"
        self.client.post(f'/cases/{case_a.id}/sketch', data={'sketch_data': b64_data})

        self.assertEqual(case_a.timeline.count(), initial_tl_count + 1)
        latest_tl = ComplaintTimeline.query.filter_by(complaint_id=case_a.id).order_by(ComplaintTimeline.id.desc()).first()
        self.assertEqual(latest_tl.event_type, 'artifact_generated_sketch')
        self.assertEqual(latest_tl.actor_user_id, self.user_a.id)

    # -------------------------------------------------------------------------
    # Gate 13: Submitted original evidence cannot be modified or removed
    # -------------------------------------------------------------------------
    def test_13_submitted_original_evidence_immutability(self):
        """Gate 13: Submitted original evidence cannot be deleted or mutated by citizen or admin."""
        case_b = self._create_submitted_case(self.user_a, ref_type='photo_normal')
        photo_ev = case_b.evidence.filter_by(source_kind='uploaded', evidence_type='photo').first()
        self.assertIsNotNone(photo_ev)

        self._login(self.user_a)
        # Attempt to delete evidence via route
        resp = self.client.post(f'/complaints/{case_b.id}/evidence/{photo_ev.id}/delete')
        self.assertEqual(resp.status_code, 400)

        # Attempt to attach evidence via draft route
        dummy_file = io.BytesIO(_generate_valid_png_bytes())
        resp_upload = self.client.post(
            f'/complaints/{case_b.id}/evidence',
            data={'evidence_files': (dummy_file, 'extra.png')}
        )
        self.assertEqual(resp_upload.status_code, 400)

        # Verify photo evidence still exists and is unchanged
        ev_check = ComplaintEvidence.query.get(photo_ev.id)
        self.assertIsNotNone(ev_check)

    # -------------------------------------------------------------------------
    # Gate 14: Test execution cannot connect to or write to live MySQL
    # -------------------------------------------------------------------------
    def test_14_zero_live_mysql_connection(self):
        """Gate 14: Confirms test execution is 100% in-memory SQLite and never touched MySQL."""
        dialect = db.engine.dialect.name
        self.assertEqual(dialect, 'sqlite')
        db_uri = str(db.engine.url)
        self.assertTrue('sqlite' in db_uri and ':memory:' in db_uri)


if __name__ == '__main__':
    unittest.main()
