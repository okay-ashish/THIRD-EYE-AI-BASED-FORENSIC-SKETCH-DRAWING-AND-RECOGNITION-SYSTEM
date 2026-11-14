from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from sqlalchemy.orm import validates
from sqlalchemy import CheckConstraint

db = SQLAlchemy()
bcrypt = Bcrypt()

# --- CONSTANTS & ROLES ---
ALLOWED_USER_ROLES = ('user', 'admin')

ALLOWED_COMPLAINT_STATUSES = (
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
)

ALLOWED_EVIDENCE_TYPES = (
    'photo',
    'audio',
    'document',
    'video',
    'sketch',
    'reconstructed_face',
    'variation',
    'poster',
    'other'
)

ALLOWED_SOURCE_KINDS = ('uploaded', 'generated')

ALLOWED_ACCESS_LEVELS = ('restricted', 'internal', 'public_notice', 'court_evidence')


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'admin' or 'user'

    # Relationships
    complaints = db.relationship(
        'Complaint',
        backref='creator',
        lazy='dynamic',
        foreign_keys='Complaint.created_by_id'
    )

    def __init__(self, username, password, role='user', full_name=None):
        if role not in ALLOWED_USER_ROLES:
            raise ValueError(f"Invalid user role: '{role}'. Allowed roles are: {ALLOWED_USER_ROLES}")
        self.username = username
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')
        self.role = role
        self.full_name = full_name

    @validates('role')
    def validate_role(self, key, role):
        if role not in ALLOWED_USER_ROLES:
            raise ValueError(f"Invalid user role: '{role}'. Allowed roles are: {ALLOWED_USER_ROLES}")
        return role

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)


class Person(db.Model):
    __tablename__ = 'persons'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # Renamed 'metadata' to 'person_details' to avoid keyword conflict
    person_details = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(200), nullable=False)
    face_encoding = db.Column(db.Text, nullable=False)


ALLOWED_FACIAL_REFERENCE_TYPES = ('none', 'photo_normal')


class Complaint(db.Model):
    __tablename__ = 'complaints'

    # Identity and ownership
    id = db.Column(db.Integer, primary_key=True)
    complaint_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reporter_relationship = db.Column(db.String(50), nullable=True)  # victim, witness, representative, other
    complainant_context = db.Column(db.Text, nullable=True)

    # Incident details (nullable for draft saving; required upon submission)
    title = db.Column(db.String(200), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    narrative = db.Column(db.Text, nullable=True)
    transcription_raw = db.Column(db.Text, nullable=True)
    incident_at = db.Column(db.DateTime, nullable=True)
    location_address = db.Column(db.String(500), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_source = db.Column(db.String(50), nullable=True)  # manual, map_pin, device
    location_notes = db.Column(db.Text, nullable=True)

    # Suspect description
    suspect_approx_age = db.Column(db.String(50), nullable=True)
    suspect_gender = db.Column(db.String(30), nullable=True)
    suspect_height = db.Column(db.String(50), nullable=True)
    suspect_build = db.Column(db.String(50), nullable=True)
    suspect_complexion = db.Column(db.String(50), nullable=True)
    suspect_hair = db.Column(db.String(100), nullable=True)
    suspect_eyes = db.Column(db.String(100), nullable=True)
    suspect_clothing = db.Column(db.Text, nullable=True)
    suspect_accessories = db.Column(db.Text, nullable=True)
    suspect_mask_description = db.Column(db.Text, nullable=True)
    suspect_identifying_marks = db.Column(db.Text, nullable=True)
    suspect_additional_details = db.Column(db.Text, nullable=True)

    # Facial reference type (Step 4 selection: none, photo_normal)
    facial_reference_type = db.Column(db.String(50), nullable=False, default='none')

    # Review and investigation
    status = db.Column(db.String(40), nullable=False, default='draft', index=True)
    assigned_officer_name = db.Column(db.String(100), nullable=True)
    assigned_officer_id = db.Column(db.String(50), nullable=True)  # staff/badge ID
    assigned_station = db.Column(db.String(100), nullable=True)
    assigned_officer_contact = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    # Table constraints and indexes
    __table_args__ = (
        db.Index('idx_complaints_status_created', 'status', 'created_at'),
        CheckConstraint(
            f"status IN {ALLOWED_COMPLAINT_STATUSES}",
            name='check_valid_complaint_status'
        ),
        CheckConstraint(
            f"facial_reference_type IN {ALLOWED_FACIAL_REFERENCE_TYPES}",
            name='check_valid_facial_reference_type'
        ),
    )

    # Relationships (non-destructive, no aggressive auto-delete)
    evidence = db.relationship(
        'ComplaintEvidence',
        backref='complaint',
        lazy='dynamic',
        order_by='ComplaintEvidence.created_at'
    )
    timeline = db.relationship(
        'ComplaintTimeline',
        backref='complaint',
        lazy='dynamic',
        order_by='ComplaintTimeline.created_at'
    )

    @validates('status')
    def validate_status(self, key, status):
        if status not in ALLOWED_COMPLAINT_STATUSES:
            raise ValueError(
                f"Invalid complaint status: '{status}'. Allowed statuses are: {ALLOWED_COMPLAINT_STATUSES}"
            )
        return status

    @validates('facial_reference_type')
    def validate_facial_reference_type(self, key, facial_reference_type):
        if facial_reference_type not in ALLOWED_FACIAL_REFERENCE_TYPES:
            raise ValueError(
                f"Invalid facial reference type: '{facial_reference_type}'. Allowed types: {ALLOWED_FACIAL_REFERENCE_TYPES}"
            )
        return facial_reference_type


class ComplaintEvidence(db.Model):
    __tablename__ = 'complaint_evidence'

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    source_evidence_id = db.Column(db.Integer, db.ForeignKey('complaint_evidence.id'), nullable=True, index=True)

    evidence_type = db.Column(db.String(50), nullable=False, default='photo')  # photo, audio, document, video, sketch, etc.
    source_kind = db.Column(db.String(20), nullable=False, default='uploaded')  # uploaded, generated
    storage_path = db.Column(db.String(500), unique=True, nullable=False)  # relative path, never absolute
    original_filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    file_size_bytes = db.Column(db.BigInteger, nullable=True)
    sha256_hex = db.Column(db.String(64), nullable=True)
    generation_method = db.Column(db.String(200), nullable=True)
    access_level = db.Column(db.String(50), nullable=False, default='restricted')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    uploader = db.relationship('User', foreign_keys=[uploaded_by_id], backref='uploaded_evidence')
    source_evidence = db.relationship('ComplaintEvidence', remote_side=[id], backref='derived_evidence')

    @validates('evidence_type')
    def validate_evidence_type(self, key, evidence_type):
        if evidence_type not in ALLOWED_EVIDENCE_TYPES:
            raise ValueError(
                f"Invalid evidence type: '{evidence_type}'. Allowed types: {ALLOWED_EVIDENCE_TYPES}"
            )
        return evidence_type

    @validates('source_kind')
    def validate_source_kind(self, key, source_kind):
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise ValueError(
                f"Invalid source kind: '{source_kind}'. Allowed kinds: {ALLOWED_SOURCE_KINDS}"
            )
        return source_kind


class ComplaintTimeline(db.Model):
    __tablename__ = 'complaint_timeline'

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    event_type = db.Column(db.String(100), nullable=False)  # created, status_changed, officer_assigned, etc.
    previous_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=True)
    message = db.Column(db.Text, nullable=True)
    is_visible_to_user = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index('idx_timeline_complaint_created', 'complaint_id', 'created_at'),
    )

    # Relationships
    actor = db.relationship('User', foreign_keys=[actor_user_id], backref='timeline_events')
