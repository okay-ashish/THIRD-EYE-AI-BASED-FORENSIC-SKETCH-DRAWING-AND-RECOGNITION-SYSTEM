"""
ThirdEye Phase 2 Test Suite: Complaint Database Models & Two-Role Foundation
=============================================================================
Verifies additive SQLAlchemy models, role validation, relationships,
and SQLite test isolation without touching the production database.

Test Coverage:
1. Registration & creation of complaints, complaint_evidence, complaint_timeline
2. Persistence of existing users and persons table definitions
3. Synthetic user complaint creation
4. Required constraints (ownership, uniqueness of complaint_number)
5. Status validation (allowed statuses vs invalid rejection)
6. Two-role restriction ('user' and 'admin' only, rejecting 'officer', etc.)
7. Evidence metadata linking without storing binary file bytes
8. Timeline events linking and chronological retrieval
9. User-complaint ORM relationships
10. Schema verification: zero binary/BLOB columns
11. Absolute database isolation verification (SQLite only, 0 MySQL writes)
"""

import unittest
import os
import sys
from datetime import datetime

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

import sqlalchemy
from sqlalchemy.exc import IntegrityError

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
    ALLOWED_EVIDENCE_TYPES,
)


class Phase2ComplaintModelsTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.drop_all()

    def setUp(self):
        """Set up fresh SQLite database session for each test."""
        self.app = app
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Double-check fail-closed isolation in every test
        dialect = db.engine.dialect.name
        if dialect != "sqlite":
            raise RuntimeError(f"TEST ABORTED: Engine is '{dialect}', expected 'sqlite'!")

        # Rollback any uncommitted transaction from previous tests
        db.session.rollback()

    def tearDown(self):
        """Tear down database session after each test."""
        db.session.rollback()
        self.app_context.pop()

    def test_01_tables_registered_and_created(self):
        """Gate 1: Verify all three new tables are registered and present in SQLite schema."""
        inspector = sqlalchemy.inspect(db.engine)
        tables = set(inspector.get_table_names())
        self.assertIn("complaints", tables)
        self.assertIn("complaint_evidence", tables)
        self.assertIn("complaint_timeline", tables)

    def test_02_existing_users_and_persons_tables(self):
        """Gate 2: Verify existing users and persons table definitions remain intact."""
        inspector = sqlalchemy.inspect(db.engine)
        tables = set(inspector.get_table_names())
        self.assertIn("users", tables)
        self.assertIn("persons", tables)

        user_cols = {col["name"] for col in inspector.get_columns("users")}
        self.assertTrue({"id", "username", "password", "role", "full_name"}.issubset(user_cols))

        person_cols = {col["name"] for col in inspector.get_columns("persons")}
        self.assertTrue({"id", "name", "person_details", "image_path", "face_encoding"}.issubset(person_cols))

    def test_03_synthetic_user_can_create_complaint(self):
        """Gate 3: Verify a synthetic user can create a valid complaint record."""
        user = User(
            username="synth_p2_creator",
            password="SecurePassword123!",
            role="user",
            full_name="Jane Doe"
        )
        db.session.add(user)
        db.session.commit()

        complaint = Complaint(
            complaint_number="CMP-2026-0001",
            created_by_id=user.id,
            reporter_relationship="victim",
            title="Attempted burglary report",
            category="Burglary",
            narrative="Witnessed an unknown individual attempting to force entry into the premises.",
            incident_at=datetime(2026, 10, 10, 14, 30),
            location_address="123 Forensic Way, Sector 4",
            latitude=13.0827,
            longitude=80.2707,
            location_source="manual",
            suspect_gender="Male",
            suspect_approx_age="30-35",
            suspect_clothing="Dark hoodie and blue jeans",
            status="draft"
        )
        db.session.add(complaint)
        db.session.commit()

        # Query back and verify
        saved = Complaint.query.filter_by(complaint_number="CMP-2026-0001").first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.title, "Attempted burglary report")
        self.assertEqual(saved.created_by_id, user.id)
        self.assertEqual(saved.status, "draft")
        self.assertEqual(saved.reporter_relationship, "victim")
        self.assertIsNotNone(saved.created_at)

    def test_04_complaint_required_constraints(self):
        """Gate 4: Verify required ownership and complaint_number uniqueness constraints."""
        user = User(
            username="synth_p2_owner_check",
            password="SecurePassword123!",
            role="user"
        )
        db.session.add(user)
        db.session.commit()

        # Uniqueness violation test
        c1 = Complaint(
            complaint_number="CMP-UNIQUE-01",
            created_by_id=user.id,
            title="First Case",
            category="Theft",
            narrative="Case narrative."
        )
        db.session.add(c1)
        db.session.commit()

        c2 = Complaint(
            complaint_number="CMP-UNIQUE-01",  # duplicate number
            created_by_id=user.id,
            title="Second Case with duplicate number",
            category="Theft",
            narrative="Another narrative."
        )
        db.session.add(c2)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_05_status_validation_accepts_and_rejects(self):
        """Gate 5: Verify all allowed statuses are accepted and invalid statuses are rejected."""
        user = User(username="synth_p2_status_user", password="Password123!", role="user")
        db.session.add(user)
        db.session.commit()

        complaint = Complaint(
            complaint_number="CMP-STATUS-TEST",
            created_by_id=user.id,
            title="Status validation test",
            category="Assault",
            narrative="Narrative text."
        )
        db.session.add(complaint)
        db.session.commit()

        # Test all valid statuses
        for valid_status in ALLOWED_COMPLAINT_STATUSES:
            complaint.status = valid_status
            db.session.commit()
            self.assertEqual(complaint.status, valid_status)

        # Test invalid status rejects via ORM validation
        with self.assertRaises(ValueError):
            complaint.status = "invalid_status"

        with self.assertRaises(ValueError):
            complaint.status = "deleted"

        with self.assertRaises(ValueError):
            complaint.status = "pending"

        db.session.rollback()

    def test_06_role_validation_two_roles_only(self):
        """Gate 6: Verify exactly two roles ('user' and 'admin') are permitted, rejecting others."""
        # 1. 'user' role works
        u1 = User(username="synth_role_user", password="Password123!", role="user")
        db.session.add(u1)
        db.session.commit()
        self.assertEqual(u1.role, "user")

        # 2. 'admin' role works
        u2 = User(username="synth_role_admin", password="Password123!", role="admin")
        db.session.add(u2)
        db.session.commit()
        self.assertEqual(u2.role, "admin")

        # 3. Third roles ('officer', 'investigator', 'superadmin') are strictly rejected
        for forbidden_role in ("officer", "investigator", "superadmin", "guest", "moderator"):
            with self.assertRaises(ValueError):
                User(username=f"synth_{forbidden_role}", password="Password123!", role=forbidden_role)

        # 4. Modifying an existing user's role to forbidden role also rejects
        with self.assertRaises(ValueError):
            u1.role = "officer"

        db.session.rollback()

    def test_07_evidence_metadata_linking_without_file_bytes(self):
        """Gate 7: Verify evidence metadata links to complaint without binary file blobs."""
        user = User(username="synth_p2_ev_user", password="Password123!", role="user")
        db.session.add(user)
        db.session.commit()

        complaint = Complaint(
            complaint_number="CMP-EV-001",
            created_by_id=user.id,
            title="Evidence link test",
            category="Robbery",
            narrative="Bank robbery evidence."
        )
        db.session.add(complaint)
        db.session.commit()

        # Add primary evidence (uploaded photo)
        photo_ev = ComplaintEvidence(
            complaint_id=complaint.id,
            uploaded_by_id=user.id,
            evidence_type="photo",
            source_kind="uploaded",
            storage_path="instance/case_storage/CMP-EV-001/cctv_frame_01.jpg",
            original_filename="cctv_frame_01.jpg",
            mime_type="image/jpeg",
            file_size_bytes=245800,
            sha256_hex="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            access_level="restricted"
        )
        db.session.add(photo_ev)
        db.session.commit()

        # Add derived evidence (generated sketch linked to source evidence)
        derived_ev = ComplaintEvidence(
            complaint_id=complaint.id,
            uploaded_by_id=user.id,
            source_evidence_id=photo_ev.id,
            evidence_type="sketch",
            source_kind="generated",
            storage_path="instance/case_storage/CMP-EV-001/derived_sketch_01.png",
            original_filename="derived_sketch_01.png",
            mime_type="image/png",
            file_size_bytes=184200,
            generation_method="Photo-to-Sketch bilateral filter engine",
            access_level="restricted"
        )
        db.session.add(derived_ev)
        db.session.commit()

        # Query and verify linking and derivation
        ev_items = complaint.evidence.all()
        self.assertEqual(len(ev_items), 2)
        self.assertEqual(derived_ev.source_evidence.id, photo_ev.id)
        self.assertIn(derived_ev, photo_ev.derived_evidence)

    def test_08_timeline_events_linking(self):
        """Gate 8: Verify timeline events link to complaint and actor in chronological order."""
        user = User(username="synth_p2_tl_user", password="Password123!", role="user")
        db.session.add(user)
        db.session.commit()

        complaint = Complaint(
            complaint_number="CMP-TL-001",
            created_by_id=user.id,
            title="Timeline case",
            category="Fraud",
            narrative="Fraudulent transaction report."
        )
        db.session.add(complaint)
        db.session.commit()

        t1 = ComplaintTimeline(
            complaint_id=complaint.id,
            actor_user_id=user.id,
            event_type="complaint_created",
            previous_status=None,
            new_status="draft",
            message="Complaint draft saved by reporter.",
            is_visible_to_user=True
        )
        t2 = ComplaintTimeline(
            complaint_id=complaint.id,
            actor_user_id=user.id,
            event_type="status_changed",
            previous_status="draft",
            new_status="submitted",
            message="Complaint formally submitted for police review.",
            is_visible_to_user=True
        )
        t3 = ComplaintTimeline(
            complaint_id=complaint.id,
            actor_user_id=None,  # system internal note
            event_type="internal_investigation_note",
            previous_status="submitted",
            new_status="submitted",
            message="Internal preliminary assessment flagged high urgency.",
            is_visible_to_user=False  # hidden from user by default
        )
        db.session.add_all([t1, t2, t3])
        db.session.commit()

        events = complaint.timeline.all()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].event_type, "complaint_created")
        self.assertEqual(events[1].event_type, "status_changed")
        self.assertEqual(events[2].event_type, "internal_investigation_note")
        self.assertFalse(events[2].is_visible_to_user)

    def test_09_user_complaints_relationship(self):
        """Gate 9: Verify User.complaints dynamic relationship returns user's cases."""
        user = User(username="synth_p2_rel_user", password="Password123!", role="user")
        db.session.add(user)
        db.session.commit()

        c1 = Complaint(
            complaint_number="CMP-REL-01",
            created_by_id=user.id,
            title="Case 1",
            category="Theft",
            narrative="Narrative 1"
        )
        c2 = Complaint(
            complaint_number="CMP-REL-02",
            created_by_id=user.id,
            title="Case 2",
            category="Cybercrime",
            narrative="Narrative 2"
        )
        db.session.add_all([c1, c2])
        db.session.commit()

        user_cases = user.complaints.all()
        self.assertEqual(len(user_cases), 2)
        self.assertEqual(c1.creator.id, user.id)
        self.assertEqual(c2.creator.id, user.id)

    def test_10_no_binary_blob_columns_in_schema(self):
        """Gate 10: Verify schema contains zero binary/BLOB columns for raw file storage."""
        inspector = sqlalchemy.inspect(db.engine)
        for table_name in ("complaints", "complaint_evidence", "complaint_timeline"):
            cols = inspector.get_columns(table_name)
            for col in cols:
                col_type_str = str(col["type"]).upper()
                self.assertNotIn("BLOB", col_type_str, f"Found BLOB in {table_name}.{col['name']}")
                self.assertNotIn("BINARY", col_type_str, f"Found BINARY in {table_name}.{col['name']}")
                self.assertNotIn("BYTEA", col_type_str, f"Found BYTEA in {table_name}.{col['name']}")

    def test_11_zero_writes_to_live_mysql(self):
        """Gate 11: Confirm execution strictly runs in SQLite without live MySQL access."""
        dialect = db.engine.dialect.name
        self.assertEqual(dialect, "sqlite")
        self.assertEqual(str(db.engine.url), "sqlite:///:memory:")


if __name__ == "__main__":
    unittest.main()
