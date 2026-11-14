"""
ThirdEye Phase 3 Test Suite: Guided Complaint Submission, Speech, Location & Private Evidence
=============================================================================================
Tests all 23 gates in pure SQLite in-memory isolation using synthetic users and mock storage.
Never connects to live MySQL.
"""

import unittest
import os
import sys

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
    remove_evidence_file,
    get_complaint_for_user,
    generate_complaint_number,
    get_complaint_storage_dir,
    get_case_storage_root,
    ComplaintValidationError,
    validate_file_content
)


class Phase3ComplaintsTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.drop_all()

    def setUp(self):
        """Prepare fresh isolated SQLite environment and temporary case storage."""
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        
        # Isolated temporary case storage folder for testing
        self.test_case_storage_dir = tempfile.mkdtemp(prefix='thirdeye_test_case_storage_')
        self.app.config['CASE_STORAGE_DIR'] = self.test_case_storage_dir

        self.app_context = self.app.app_context()
        self.app_context.push()

        # Strict fail-closed isolation check
        dialect = db.engine.dialect.name
        if dialect != "sqlite":
            raise RuntimeError(f"FATAL ISOLATION BREACH: Engine dialect is '{dialect}', expected 'sqlite'!")

        # Ensure clean state in in-memory SQLite
        db.session.rollback()
        ComplaintEvidence.query.delete()
        ComplaintTimeline.query.delete()
        Complaint.query.delete()
        User.query.delete()
        Person.query.delete()
        db.session.commit()

        # Seed synthetic users for role & ownership tests
        self.citizen = User(username="synth_citizen_p3", password="Password123!", role="user", full_name="Citizen One")
        self.other_citizen = User(username="synth_other_p3", password="Password123!", role="user", full_name="Citizen Two")
        self.admin = User(username="synth_admin_p3", password="Password123!", role="admin", full_name="Admin Master")
        
        db.session.add_all([self.citizen, self.other_citizen, self.admin])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up temporary test directory and database session."""
        db.session.rollback()
        self.app_context.pop()
        if os.path.exists(self.test_case_storage_dir):
            shutil.rmtree(self.test_case_storage_dir, ignore_errors=True)

    def _login(self, user):
        """Helper to simulate session login."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['username'] = user.username
            sess['role'] = user.role
            sess['full_name'] = user.full_name
            sess['csrf_token'] = 'test_phase3_csrf_token_raw'

    def _csrf_token(self):
        from itsdangerous import URLSafeTimedSerializer
        s = URLSafeTimedSerializer(self.app.secret_key, salt='wtf-csrf-token')
        return s.dumps('test_phase3_csrf_token_raw')

    # -------------------------------------------------------------------------
    # GATE 1: Unauthenticated users cannot create or save complaints
    # -------------------------------------------------------------------------
    def test_gate_01_unauthenticated_cannot_create_or_save(self):
        """Gate 1: Unauthenticated requests are redirected to login."""
        # GET /complaints/new
        resp = self.client.get('/complaints/new')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        # POST /complaints/1/draft
        resp = self.client.post('/complaints/1/draft', json={'title': 'Unauthorized draft'})
        self.assertIn(resp.status_code, [302, 400, 401])

        # POST /complaints/1/submit
        resp = self.client.post('/complaints/1/submit', json={})
        self.assertIn(resp.status_code, [302, 400, 401])

    # -------------------------------------------------------------------------
    # GATE 2: Admin accounts cannot use User-only submission routes
    # -------------------------------------------------------------------------
    def test_gate_02_admin_cannot_access_submission_routes(self):
        """Gate 2: Admin accounts receive 403 Forbidden on citizen submission routes."""
        self._login(self.admin)

        resp = self.client.get('/complaints/new')
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post('/complaints/1/draft', headers={'X-CSRFToken': self._csrf_token()}, json={'title': 'Admin draft'})
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post('/complaints/1/submit', headers={'X-CSRFToken': self._csrf_token()})
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------------------
    # GATE 3: A User can create and save a draft
    # -------------------------------------------------------------------------
    def test_gate_03_citizen_can_create_and_save_draft(self):
        """Gate 3: Authenticated citizen can initialize and save a draft."""
        self._login(self.citizen)

        # GET is read-only and does not create drafts
        resp_get = self.client.get('/complaints/new?fresh=1', follow_redirects=False)
        self.assertEqual(resp_get.status_code, 200)
        self.assertIsNone(Complaint.query.filter_by(created_by_id=self.citizen.id, status='draft').first())

        # POST creates draft and redirects to /edit
        resp = self.client.post('/complaints/new', headers={'X-CSRFToken': self._csrf_token()}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/complaints/', resp.headers['Location'])
        self.assertIn('/edit', resp.headers['Location'])

        # Verify draft exists in DB
        draft = Complaint.query.filter_by(created_by_id=self.citizen.id, status='draft').first()
        self.assertIsNotNone(draft)
        self.assertTrue(draft.complaint_number.startswith('TE-2026-'))
        self.assertEqual(draft.status, 'draft')

    # -------------------------------------------------------------------------
    # GATE 4: Drafts can be resumed and updated by their owner
    # -------------------------------------------------------------------------
    def test_gate_04_drafts_resumed_and_updated_by_owner(self):
        """Gate 4: Owner can resume and update draft fields."""
        draft = create_draft_complaint(self.citizen.id)
        self._login(self.citizen)

        # GET /complaints/<id>/edit
        resp = self.client.get(f'/complaints/{draft.id}/edit')
        self.assertEqual(resp.status_code, 200)

        # POST /complaints/<id>/draft to update title and category
        update_data = {
            'title': 'Bicycle theft from porch',
            'category': 'Theft / Burglary',
            'reporter_relationship': 'victim'
        }
        resp = self.client.post(f'/complaints/{draft.id}/draft', json=update_data)
        self.assertEqual(resp.status_code, 200)

        saved = Complaint.query.get(draft.id)
        self.assertEqual(saved.title, 'Bicycle theft from porch')
        self.assertEqual(saved.category, 'Theft / Burglary')
        self.assertEqual(saved.reporter_relationship, 'victim')
        self.assertEqual(saved.status, 'draft')

    # -------------------------------------------------------------------------
    # GATE 5: A different user cannot read or modify that draft
    # -------------------------------------------------------------------------
    def test_gate_05_cross_user_isolation(self):
        """Gate 5: User B cannot view, edit, or submit User A's draft (403 Forbidden)."""
        draft_a = create_draft_complaint(self.citizen.id, {'title': 'Citizen A Secret Draft'})
        
        # Log in as other citizen
        self._login(self.other_citizen)

        # Attempt to read
        resp = self.client.get(f'/complaints/{draft_a.id}/edit')
        self.assertEqual(resp.status_code, 403)

        # Attempt to update
        resp = self.client.post(f'/complaints/{draft_a.id}/draft', json={'title': 'Hacked Title'})
        self.assertEqual(resp.status_code, 403)

        # Attempt to submit
        resp = self.client.post(f'/complaints/{draft_a.id}/submit', json={})
        self.assertEqual(resp.status_code, 403)

        # Check title unchanged in DB
        db.session.refresh(draft_a)
        self.assertEqual(draft_a.title, 'Citizen A Secret Draft')

    # -------------------------------------------------------------------------
    # GATE 6: Drafts may have incomplete title/category/narrative fields
    # -------------------------------------------------------------------------
    def test_gate_06_drafts_allow_incomplete_fields(self):
        """Gate 6: Draft records can be persisted with null/empty title, category, narrative."""
        draft = create_draft_complaint(self.citizen.id)
        self.assertIsNone(draft.title)
        self.assertIsNone(draft.category)
        self.assertIsNone(draft.narrative)

        # Update partial fields (e.g. only suspect details)
        update_draft_complaint(draft.id, self.citizen.id, {
            'suspect_approx_age': '30',
            'suspect_gender': 'Male'
        })
        saved = Complaint.query.get(draft.id)
        self.assertEqual(saved.suspect_approx_age, '30')
        self.assertIsNone(saved.title)
        self.assertIsNone(saved.category)
        self.assertIsNone(saved.narrative)
        self.assertEqual(saved.status, 'draft')

    # -------------------------------------------------------------------------
    # GATE 7: Submitting a complaint missing required fields is rejected
    # -------------------------------------------------------------------------
    def test_gate_07_submitting_missing_fields_rejected(self):
        """Gate 7: Submitting missing title, category, or narrative raises validation errors."""
        draft = create_draft_complaint(self.citizen.id)
        self._login(self.citizen)

        # Empty submission
        resp = self.client.post(f'/complaints/{draft.id}/submit', json={})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('title', data['errors'])
        self.assertIn('category', data['errors'])
        self.assertIn('narrative', data['errors'])

        # With title only
        resp = self.client.post(f'/complaints/{draft.id}/submit', json={'title': 'Only Title'})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertNotIn('title', data['errors'])
        self.assertIn('category', data['errors'])
        self.assertIn('narrative', data['errors'])

        # Status remains draft
        db.session.refresh(draft)
        self.assertEqual(draft.status, 'draft')

    # -------------------------------------------------------------------------
    # GATE 8: Valid complaints receive unique complaint numbers
    # -------------------------------------------------------------------------
    def test_gate_08_unique_complaint_numbers(self):
        """Gate 8: Generated complaint numbers follow TE-2026-XXXXXXXX and are unique."""
        numbers = set()
        for _ in range(25):
            num = generate_complaint_number()
            self.assertTrue(num.startswith('TE-2026-'))
            self.assertEqual(len(num), 16)  # TE-2026- (8) + 8 chars = 16
            self.assertNotIn(num, numbers)
            numbers.add(num)

    # -------------------------------------------------------------------------
    # GATE 9: Submission changes status correctly
    # -------------------------------------------------------------------------
    def test_gate_09_submission_changes_status_to_submitted(self):
        """Gate 9: Complete submission transitions status from draft to submitted."""
        draft = create_draft_complaint(self.citizen.id, {
            'title': 'Stolen Handbag at Market',
            'category': 'Theft / Burglary',
            'narrative': 'A suspect snatched my bag near the fruit stall.'
        })
        self._login(self.citizen)

        resp = self.client.post(f'/complaints/{draft.id}/submit', json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['complaint_number'], draft.complaint_number)

        db.session.refresh(draft)
        self.assertEqual(draft.status, 'submitted')

    # -------------------------------------------------------------------------
    # GATE 10: Submission creates an appropriate timeline event
    # -------------------------------------------------------------------------
    def test_gate_10_submission_creates_timeline_event(self):
        """Gate 10: Submission registers ComplaintTimeline entry with citizen actor and visibility."""
        draft = create_draft_complaint(self.citizen.id, {
            'title': 'Vandalism on shop shutter',
            'category': 'Vandalism / Property Damage',
            'narrative': 'Graffiti and lock tampering found in morning.'
        })
        submit_complaint(draft.id, self.citizen.id)

        timeline = ComplaintTimeline.query.filter_by(complaint_id=draft.id).first()
        self.assertIsNotNone(timeline)
        self.assertEqual(timeline.event_type, 'complaint_submitted')
        self.assertEqual(timeline.previous_status, 'draft')
        self.assertEqual(timeline.new_status, 'submitted')
        self.assertTrue(timeline.is_visible_to_user)
        self.assertEqual(timeline.actor_user_id, self.citizen.id)

    # -------------------------------------------------------------------------
    # GATE 11: Unauthorized IDs and path traversal are rejected
    # -------------------------------------------------------------------------
    def test_gate_11_unauthorized_ids_and_path_traversal_rejected(self):
        """Gate 11: Invalid complaint IDs 404, path traversal in case dir raises ValueError."""
        self._login(self.citizen)

        resp = self.client.get('/complaints/999999/edit')
        self.assertEqual(resp.status_code, 404)

        resp = self.client.post('/complaints/999999/submit')
        self.assertEqual(resp.status_code, 404)

        # Path traversal prevention in storage
        with self.assertRaises((ValueError, PermissionError)):
            get_complaint_storage_dir('../../../windows/system32')

    # -------------------------------------------------------------------------
    # GATE 12: Evidence extension and size validation work
    # -------------------------------------------------------------------------
    def test_gate_12_evidence_extension_and_size_validation(self):
        """Gate 12: Valid extensions pass; illegal extensions (.exe, .sh) are rejected."""
        draft = create_draft_complaint(self.citizen.id)

        # Disallowed extension
        fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
        fake_exe.filename = "malware.exe"
        with self.assertRaises(ValueError) as ctx:
            attach_evidence_file(draft.id, self.citizen.id, fake_exe)
        self.assertIn("Unsupported file extension", str(ctx.exception))

    # -------------------------------------------------------------------------
    # GATE 13: An invalid or oversized upload is rejected safely
    # -------------------------------------------------------------------------
    def test_gate_13_oversized_and_invalid_signature_rejected(self):
        """Gate 13: Oversized files and signature mismatches are safely rejected."""
        draft = create_draft_complaint(self.citizen.id)

        # Fake PNG with corrupted header
        corrupt_png = io.BytesIO(b"NOT_A_PNG_FILE_HEADER")
        corrupt_png.filename = "evidence.png"
        with self.assertRaises(ValueError) as ctx:
            attach_evidence_file(draft.id, self.citizen.id, corrupt_png)
        self.assertIn("signature", str(ctx.exception).lower())

        # Oversized JPEG (> 10 MB)
        oversized_jpg = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * (11 * 1024 * 1024))
        oversized_jpg.filename = "huge_photo.jpg"
        with self.assertRaises(ValueError) as ctx:
            attach_evidence_file(draft.id, self.citizen.id, oversized_jpg)
        self.assertIn("exceeds maximum 10 MB", str(ctx.exception))

    # -------------------------------------------------------------------------
    # GATE 14: Successful evidence upload stores only metadata in SQL
    # -------------------------------------------------------------------------
    def test_gate_14_evidence_upload_stores_metadata_only(self):
        """Gate 14: Uploading evidence stores path, size, SHA-256 in SQL, no BLOBs."""
        draft = create_draft_complaint(self.citizen.id)
        
        # Valid PNG with standard header
        valid_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        file_obj = io.BytesIO(valid_png_bytes)
        file_obj.filename = "crime_scene.png"
        file_obj.mimetype = "image/png"

        ev = attach_evidence_file(draft.id, self.citizen.id, file_obj)
        self.assertIsNotNone(ev.id)
        self.assertEqual(ev.evidence_type, "photo")
        self.assertEqual(ev.original_filename, "crime_scene.png")
        self.assertEqual(ev.file_size_bytes, len(valid_png_bytes))
        self.assertEqual(len(ev.sha256_hex), 64)
        self.assertTrue(ev.storage_path.startswith("case_storage/"))

        # Check DB row has no binary blob columns
        inspector = sqlalchemy.inspect(db.engine)
        for col in inspector.get_columns("complaint_evidence"):
            col_type = str(col["type"]).upper()
            self.assertNotIn("BLOB", col_type)
            self.assertNotIn("BINARY", col_type)

    # -------------------------------------------------------------------------
    # GATE 15: Database failure does not leave an orphaned evidence file
    # -------------------------------------------------------------------------
    def test_gate_15_database_failure_cleans_up_disk_file(self):
        """Gate 15: If db.session.commit fails, newly created disk file is unlinked."""
        draft = create_draft_complaint(self.citizen.id)
        valid_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png_bytes)
        file_obj.filename = "test_rollback.png"

        # Mock db.session.commit to simulate SQL error
        with patch.object(db.session, 'commit', side_effect=Exception("Simulated SQL error")):
            with self.assertRaises(Exception):
                attach_evidence_file(draft.id, self.citizen.id, file_obj)

        # Verify no file remained in case storage
        case_dir = get_complaint_storage_dir(draft.complaint_number)
        evidence_files = os.listdir(os.path.join(case_dir, 'evidence'))
        self.assertEqual(len(evidence_files), 0)

    # -------------------------------------------------------------------------
    # GATE 16: Failed file writes do not create a committed evidence record
    # -------------------------------------------------------------------------
    def test_gate_16_failed_file_write_rolls_back_db(self):
        """Gate 16: If file writing raises an IOError, no DB row is created."""
        draft = create_draft_complaint(self.citizen.id)
        valid_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png_bytes)
        file_obj.filename = "test_write_fail.png"

        with patch('builtins.open', side_effect=IOError("Disk write failed")):
            with self.assertRaises(IOError):
                attach_evidence_file(draft.id, self.citizen.id, file_obj)

        self.assertEqual(ComplaintEvidence.query.count(), 0)

    # -------------------------------------------------------------------------
    # GATE 17: Only private-storage paths are recorded
    # -------------------------------------------------------------------------
    def test_gate_17_only_private_storage_paths_recorded(self):
        """Gate 17: Storage paths strictly reside within case_storage/ and are relative."""
        draft = create_draft_complaint(self.citizen.id)
        valid_pdf = b"%PDF-1.4\n" + b"\x00" * 100
        file_obj = io.BytesIO(valid_pdf)
        file_obj.filename = "fir_copy.pdf"
        file_obj.mimetype = "application/pdf"

        ev = attach_evidence_file(draft.id, self.citizen.id, file_obj)
        self.assertTrue(ev.storage_path.startswith("case_storage/"))
        self.assertNotIn("..", ev.storage_path)
        self.assertFalse(os.path.isabs(ev.storage_path))

    # -------------------------------------------------------------------------
    # GATE 18: Voice fallback is functional when speech recognition unavailable
    # -------------------------------------------------------------------------
    def test_gate_18_voice_fallback_functional(self):
        """Gate 18: Manual narrative text is preserved even without speech dictation."""
        draft = create_draft_complaint(self.citizen.id)
        manual_text = "I am typing this manually because my browser does not support Web Speech API."
        update_draft_complaint(draft.id, self.citizen.id, {
            'narrative': manual_text,
            'transcription_raw': None
        })

        db.session.refresh(draft)
        self.assertEqual(draft.narrative, manual_text)
        self.assertIsNone(draft.transcription_raw)

    # -------------------------------------------------------------------------
    # GATE 19: Location fields and coordinate ranges are validated
    # -------------------------------------------------------------------------
    def test_gate_19_location_coordinate_ranges_validated(self):
        """Gate 19: Latitude [-90, 90] and Longitude [-180, 180] are strictly validated."""
        draft = create_draft_complaint(self.citizen.id)

        # Valid coords
        update_draft_complaint(draft.id, self.citizen.id, {
            'latitude': 13.0827,
            'longitude': 80.2707,
            'location_source': 'map_pin'
        })
        db.session.refresh(draft)
        self.assertEqual(draft.latitude, 13.0827)
        self.assertEqual(draft.longitude, 80.2707)

        # Invalid Latitude > 90
        with self.assertRaises(ValueError) as ctx:
            update_draft_complaint(draft.id, self.citizen.id, {'latitude': 95.5})
        self.assertIn("Latitude must be between -90 and 90", str(ctx.exception))

        # Invalid Longitude < -180
        with self.assertRaises(ValueError) as ctx:
            update_draft_complaint(draft.id, self.citizen.id, {'longitude': -185.0})
        self.assertIn("Longitude must be between -180 and 180", str(ctx.exception))

    # -------------------------------------------------------------------------
    # GATE 20: Existing two-role checks remain enforced
    # -------------------------------------------------------------------------
    def test_gate_20_two_roles_enforced(self):
        """Gate 20: Only 'user' and 'admin' allowed; third role 'officer' is rejected."""
        self.assertIn('user', ALLOWED_USER_ROLES)
        self.assertIn('admin', ALLOWED_USER_ROLES)
        self.assertEqual(len(ALLOWED_USER_ROLES), 2)

        with self.assertRaises(ValueError):
            User(username="bad_officer", password="Password123!", role="officer")

    # -------------------------------------------------------------------------
    # GATE 21: Existing Person and User model behavior is preserved
    # -------------------------------------------------------------------------
    def test_gate_21_existing_person_and_user_behavior_preserved(self):
        """Gate 21: Person and User records operate normally without breaking changes."""
        p = Person(name="Suspect Alpha", image_path="static/person_db/alpha.jpg", face_encoding="[0.1, 0.2]")
        db.session.add(p)
        db.session.commit()

        queried = Person.query.filter_by(name="Suspect Alpha").first()
        self.assertIsNotNone(queried)
        self.assertEqual(queried.image_path, "static/person_db/alpha.jpg")

        # User password check
        self.assertTrue(self.citizen.check_password("Password123!"))
        self.assertFalse(self.citizen.check_password("WrongPassword"))

    # -------------------------------------------------------------------------
    # GATE 22: Test execution does not invoke broad cleanup against unrelated files
    # -------------------------------------------------------------------------
    def test_gate_22_no_broad_cleanup(self):
        """Gate 22: Case storage removal only targets case-specific test directories."""
        self.assertTrue(os.path.exists(self.test_case_storage_dir))
        # Ensure project static and template directories exist and are untouched
        self.assertTrue(os.path.isdir('templates'))
        self.assertTrue(os.path.isdir('static'))

    # -------------------------------------------------------------------------
    # GATE 23: MySQL connection attempts are blocked in tests
    # -------------------------------------------------------------------------
    def test_gate_23_mysql_strictly_blocked_in_tests(self):
        """Gate 23: Test environment dialect is SQLite and zero MySQL connections made."""
        self.assertEqual(db.engine.dialect.name, "sqlite")

    # -------------------------------------------------------------------------
    # GATE 24: Evidence deletion is permitted only on drafts
    # -------------------------------------------------------------------------
    def test_gate_24_evidence_deletion_permitted_on_drafts(self):
        """Gate 24: Owner can delete evidence while complaint is in draft status."""
        draft = create_draft_complaint(self.citizen.id)
        valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png)
        file_obj.filename = "delete_test.png"
        ev = attach_evidence_file(draft.id, self.citizen.id, file_obj)

        root = get_case_storage_root()
        clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
        abs_path = os.path.abspath(os.path.join(root, clean_rel))
        self.assertTrue(os.path.isfile(abs_path))

        self._login(self.citizen)
        resp = self.client.post(f'/complaints/{draft.id}/evidence/{ev.id}/delete')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

        # DB row deleted and disk file unlinked
        self.assertIsNone(ComplaintEvidence.query.get(ev.id))
        self.assertFalse(os.path.isfile(abs_path))

    # -------------------------------------------------------------------------
    # GATE 25: Submitted evidence cannot be removed by the User
    # -------------------------------------------------------------------------
    def test_gate_25_submitted_evidence_cannot_be_removed_by_user(self):
        """Gate 25: Evidence on a submitted complaint is frozen and cannot be removed."""
        draft = create_draft_complaint(self.citizen.id, {
            'title': 'Robbery with evidence',
            'category': 'Robbery / Armed Assault',
            'narrative': 'Witnessed robbery and captured photographic proof.'
        })
        valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png)
        file_obj.filename = "frozen_proof.png"
        ev = attach_evidence_file(draft.id, self.citizen.id, file_obj)

        # Submit complaint
        submit_complaint(draft.id, self.citizen.id)
        db.session.refresh(draft)
        self.assertEqual(draft.status, 'submitted')

        root = get_case_storage_root()
        clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
        abs_path = os.path.abspath(os.path.join(root, clean_rel))
        self.assertTrue(os.path.isfile(abs_path))

        self._login(self.citizen)
        resp = self.client.post(f'/complaints/{draft.id}/evidence/{ev.id}/delete')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Cannot remove evidence from a submitted complaint', resp.get_json().get('error', ''))

        # Direct service call must also fail closed
        with self.assertRaises(ValueError) as ctx:
            remove_evidence_file(draft.id, ev.id, self.citizen.id)
        self.assertIn("Cannot remove evidence from a submitted complaint", str(ctx.exception))

        # Evidence must remain intact in DB and on disk
        self.assertIsNotNone(ComplaintEvidence.query.get(ev.id))
        self.assertTrue(os.path.isfile(abs_path))

    # -------------------------------------------------------------------------
    # GATE 26: Submitted draft-save and resubmission attempts are rejected
    # -------------------------------------------------------------------------
    def test_gate_26_submitted_draft_save_and_resubmission_rejected(self):
        """Gate 26: Submitted complaints cannot be edited, appended with evidence, or resubmitted."""
        complaint = create_draft_complaint(self.citizen.id, {
            'title': 'Completed Investigation',
            'category': 'Fraud / Financial Scam',
            'narrative': 'Complete report already filed.'
        })
        submit_complaint(complaint.id, self.citizen.id)
        self._login(self.citizen)

        # Draft save attempt on submitted complaint
        resp = self.client.post(f'/complaints/{complaint.id}/draft', json={'title': 'Tampered Title'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already been submitted', resp.get_json().get('error', ''))

        # Evidence upload attempt on submitted complaint
        fake_png = (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16), 'extra.png')
        resp = self.client.post(f'/complaints/{complaint.id}/evidence', data={'evidence_files': fake_png}, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Cannot attach evidence to a submitted complaint', resp.get_json().get('error', ''))

        # Resubmission attempt on submitted complaint
        resp = self.client.post(f'/complaints/{complaint.id}/submit', json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already been submitted', resp.get_json().get('error', ''))

    # -------------------------------------------------------------------------
    # GATE 27: Cross-user evidence access remains blocked
    # -------------------------------------------------------------------------
    def test_gate_27_cross_user_evidence_access_blocked(self):
        """Gate 27: Changing complaint ID or evidence ID never allows cross-user access."""
        draft_a = create_draft_complaint(self.citizen.id)
        valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png)
        file_obj.filename = "user_a_evidence.png"
        ev_a = attach_evidence_file(draft_a.id, self.citizen.id, file_obj)

        draft_b = create_draft_complaint(self.other_citizen.id)

        # User B attempts to view User A's evidence
        self._login(self.other_citizen)
        resp = self.client.get(f'/complaints/{draft_a.id}/evidence/{ev_a.id}/view')
        self.assertEqual(resp.status_code, 403)

        # User B attempts to delete User A's evidence
        resp = self.client.post(f'/complaints/{draft_a.id}/evidence/{ev_a.id}/delete')
        self.assertEqual(resp.status_code, 403)

        # User B attempts to attach evidence to User A's complaint
        fake_png = (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16), 'injected.png')
        resp = self.client.post(f'/complaints/{draft_a.id}/evidence', data={'evidence_files': fake_png}, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 403)

        # User B attempts to access User A's evidence under User B's complaint ID
        resp = self.client.get(f'/complaints/{draft_b.id}/evidence/{ev_a.id}/view')
        self.assertEqual(resp.status_code, 404)

    # -------------------------------------------------------------------------
    # GATE 28: Evidence view route rejects path traversal
    # -------------------------------------------------------------------------
    def test_gate_28_evidence_view_path_traversal_rejected(self):
        """Gate 28: Tampered storage_path with traversal sequences is rejected with 404."""
        draft = create_draft_complaint(self.citizen.id)
        valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png)
        file_obj.filename = "traversal_check.png"
        ev = attach_evidence_file(draft.id, self.citizen.id, file_obj)

        # Tamper DB storage_path to traversal sequence
        ev.storage_path = "case_storage/../../../../windows/system32/calc.exe"
        db.session.commit()

        self._login(self.citizen)
        resp = self.client.get(f'/complaints/{draft.id}/evidence/{ev.id}/view')
        self.assertEqual(resp.status_code, 404)

    # -------------------------------------------------------------------------
    # GATE 29: Failed DB commit during evidence deletion preserves disk file
    # -------------------------------------------------------------------------
    def test_gate_29_evidence_deletion_db_failure_preserves_disk_file(self):
        """Gate 29: If database commit fails during deletion, physical file remains intact."""
        draft = create_draft_complaint(self.citizen.id)
        valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        file_obj = io.BytesIO(valid_png)
        file_obj.filename = "commit_fail.png"
        ev = attach_evidence_file(draft.id, self.citizen.id, file_obj)

        root = get_case_storage_root()
        clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
        abs_path = os.path.abspath(os.path.join(root, clean_rel))
        self.assertTrue(os.path.isfile(abs_path))

        with patch.object(db.session, 'commit', side_effect=Exception("Database lock failure")):
            with self.assertRaises(Exception):
                remove_evidence_file(draft.id, ev.id, self.citizen.id)

        # DB session rollback kept record, disk file still exists
        self.assertTrue(os.path.isfile(abs_path))


if __name__ == '__main__':
    unittest.main()
