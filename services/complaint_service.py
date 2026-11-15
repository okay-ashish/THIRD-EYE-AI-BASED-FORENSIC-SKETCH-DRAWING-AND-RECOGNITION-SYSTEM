"""
ThirdEye Complaint Service Layer (Phase 3)
==========================================
Encapsulates business logic, validation, secure storage management,
and audit timeline creation for crime complaint workflows.

Strictly preserves:
1. Zero binary/BLOB storage in MySQL (file metadata only).
2. Fail-closed ownership & role checks ('user' role only).
3. Private storage root at instance/case_storage/<complaint_number>/.
4. Path traversal rejection and transaction safety.
5. Incomplete draft saving vs. strict required-fields validation at final submission.
"""

import os
import secrets
import hashlib
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app

from models import (
    db,
    Complaint,
    ComplaintEvidence,
    ComplaintTimeline,
    User,
    ALLOWED_FACIAL_REFERENCE_TYPES
)

# --- CONFIGURATION LIMITS ---
MAX_PHOTO_DOC_BYTES = 10 * 1024 * 1024   # 10 MB per photo or PDF
MAX_AUDIO_BYTES = 15 * 1024 * 1024       # 15 MB per audio file
MAX_TOTAL_EVIDENCE_BYTES = 40 * 1024 * 1024  # 40 MB max retained evidence per case
MAX_FILES_PER_UPLOAD = 5

ALLOWED_EXTENSIONS = {
    'photo': {'.jpg', '.jpeg', '.png', '.webp'},
    'document': {'.pdf'},
    'audio': {'.webm', '.ogg', '.wav', '.mp3', '.m4a', '.mp4'},
}

ALL_ALLOWED_EXTS = set().union(*ALLOWED_EXTENSIONS.values())

MAGIC_SIGNATURES = {
    'jpeg': b'\xff\xd8\xff',
    'png': b'\x89PNG\r\n\x1a\n',
    'pdf': b'%PDF-',
    'ogg': b'OggS',
    'webm': b'\x1a\x45\xdf\xa3',
}


class ComplaintValidationError(ValueError):
    """Raised when complaint submission validation fails."""
    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def get_case_storage_root():
    """Returns the base private storage directory for all cases."""
    if current_app:
        configured = current_app.config.get('CASE_STORAGE_DIR')
        if configured:
            return os.path.abspath(configured)
        return os.path.abspath(os.path.join(current_app.instance_path, 'case_storage'))
    # Fallback to local instance directory if outside app context
    return os.path.abspath(os.path.join('instance', 'case_storage'))


def get_complaint_storage_dir(complaint_number, create_subdirs=True):
    """
    Returns the resolved private storage directory for a specific complaint.
    Ensures safe path containment and provisions evidence/, approved_posters/, generated/.
    """
    root = get_case_storage_root()
    clean_num = secure_filename(complaint_number.strip())
    if not clean_num or clean_num != complaint_number:
        raise ValueError(f"Invalid complaint number format for storage: {complaint_number}")

    case_dir = os.path.abspath(os.path.join(root, clean_num))
    # Prevent path traversal
    if os.path.commonpath([root, case_dir]) != root:
        raise PermissionError("Path traversal attempt detected in case storage path.")

    if create_subdirs:
        for sub in ('evidence', 'approved_posters', 'generated'):
            os.makedirs(os.path.join(case_dir, sub), exist_ok=True)

    return case_dir


def generate_complaint_number():
    """
    Generates a unique, non-sequential, human-readable complaint reference.
    Format: TE-YYYY-XXXXXXXX (e.g. TE-2026-A9F4K2B1)
    Retries up to 10 times to resolve any collision.
    """
    year = datetime.utcnow().year
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # Omits 0, 1, I, O to reduce visual confusion
    for _ in range(10):
        suffix = "".join(secrets.choice(alphabet) for _ in range(8))
        candidate = f"TE-{year}-{suffix}"
        if not Complaint.query.filter_by(complaint_number=candidate).first():
            return candidate
    raise RuntimeError("Failed to generate unique complaint number after multiple retries.")


def create_draft_complaint(user_id, initial_data=None):
    """
    Creates a new complaint in 'draft' status owned by the authenticated citizen.
    Allows incomplete details.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found.")
    if user.role != 'user':
        raise PermissionError("Only citizen accounts with role 'user' may file complaints.")

    complaint_num = generate_complaint_number()
    # Initialize storage subdirectories
    get_complaint_storage_dir(complaint_num, create_subdirs=True)

    complaint = Complaint(
        complaint_number=complaint_num,
        created_by_id=user.id,
        status='draft',
        facial_reference_type='none'
    )

    if initial_data:
        apply_complaint_data(complaint, initial_data)

    db.session.add(complaint)
    db.session.commit()
    return complaint


def get_complaint_for_user(complaint_id, user_id):
    """
    Safely retrieves a complaint ensuring the current user is the owner.
    Raises PermissionError if owned by a different user.
    """
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return None
    if complaint.created_by_id != user_id:
        raise PermissionError(f"User {user_id} is not authorized to access complaint {complaint_id}.")
    return complaint


def apply_complaint_data(complaint, data):
    """
    Updates complaint fields from form dictionary.
    Allows partial/empty values for draft persistence.
    Validates coordinate ranges when present.
    """
    # Step 1: Details
    if 'title' in data:
        complaint.title = data['title'].strip() if data['title'] else None
    if 'category' in data:
        complaint.category = data['category'].strip() if data['category'] else None
    if 'reporter_relationship' in data:
        complaint.reporter_relationship = data['reporter_relationship'].strip() if data['reporter_relationship'] else None
    if 'complainant_context' in data:
        complaint.complainant_context = data['complainant_context'].strip() if data['complainant_context'] else None

    # Step 2: Time, Location, Narrative
    if 'incident_at' in data:
        val = data['incident_at']
        if isinstance(val, str) and val.strip():
            # Support HTML5 datetime-local or ISO format
            for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    complaint.incident_at = datetime.strptime(val.strip(), fmt)
                    break
                except ValueError:
                    continue
        elif isinstance(val, datetime):
            complaint.incident_at = val
        elif not val:
            complaint.incident_at = None

    if 'location_address' in data:
        loc_val = data['location_address']
        if isinstance(loc_val, str) and loc_val.strip():
            # Validate, sanitize and constrain to 500 characters
            cleaned_loc = loc_val.strip()[:500]
            complaint.location_address = cleaned_loc
        else:
            complaint.location_address = None
    if 'location_notes' in data:
        complaint.location_notes = data['location_notes'].strip() if data['location_notes'] else None
    if 'location_source' in data:
        complaint.location_source = data['location_source'].strip() if data['location_source'] else 'manual'
    if 'narrative' in data:
        complaint.narrative = data['narrative'].strip() if data['narrative'] else None
    if 'transcription_raw' in data:
        complaint.transcription_raw = data['transcription_raw'].strip() if data['transcription_raw'] else None

    # Coordinate validation
    if 'latitude' in data:
        lat = data['latitude']
        if lat is not None and lat != '':
            try:
                lat_f = float(lat)
                if not (-90.0 <= lat_f <= 90.0):
                    raise ValueError(f"Latitude must be between -90 and 90. Received: {lat_f}")
                complaint.latitude = lat_f
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid latitude value: {e}")
        else:
            complaint.latitude = None

    if 'longitude' in data:
        lon = data['longitude']
        if lon is not None and lon != '':
            try:
                lon_f = float(lon)
                if not (-180.0 <= lon_f <= 180.0):
                    raise ValueError(f"Longitude must be between -180 and 180. Received: {lon_f}")
                complaint.longitude = lon_f
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid longitude value: {e}")
        else:
            complaint.longitude = None

    # Step 3: Suspect description (all optional/unknown allowed)
    suspect_fields = [
        'suspect_approx_age', 'suspect_gender', 'suspect_height', 'suspect_build',
        'suspect_complexion', 'suspect_hair', 'suspect_eyes', 'suspect_clothing',
        'suspect_accessories', 'suspect_mask_description', 'suspect_identifying_marks',
        'suspect_additional_details'
    ]
    for field in suspect_fields:
        if field in data:
            val = data[field]
            setattr(complaint, field, val.strip() if val else None)

    # Step 4: Facial reference type
    if 'facial_reference_type' in data:
        frt = data['facial_reference_type'].strip() if data['facial_reference_type'] else 'none'
        if frt not in ALLOWED_FACIAL_REFERENCE_TYPES:
            raise ValueError(f"Invalid facial reference type: '{frt}'. Allowed: {ALLOWED_FACIAL_REFERENCE_TYPES}")
        complaint.facial_reference_type = frt

    complaint.updated_at = datetime.utcnow()


def update_draft_complaint(complaint_id, user_id, form_data):
    """
    Updates an existing draft complaint for the authenticated user.
    """
    complaint = get_complaint_for_user(complaint_id, user_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")
    if complaint.status != 'draft':
        raise ValueError("Cannot edit a complaint that has already been submitted.")

    apply_complaint_data(complaint, form_data)
    db.session.commit()
    return complaint


def validate_for_submission(complaint):
    """
    Enforces that required fields (title, category, narrative) are non-empty strings.
    Other fields (location, suspect, evidence) may remain blank or unknown.
    """
    errors = {}
    if not complaint.title or not complaint.title.strip():
        errors['title'] = 'Complaint title is required.'
    if not complaint.category or not complaint.category.strip():
        errors['category'] = 'Incident category is required.'
    if not complaint.narrative or not complaint.narrative.strip():
        errors['narrative'] = 'Written incident narrative is required.'

    if errors:
        raise ComplaintValidationError(errors)


def submit_complaint(complaint_id, user_id):
    """
    Validates and finalizes complaint submission:
    1. Verifies ownership and draft status.
    2. Validates non-empty title, category, narrative.
    3. Changes status to 'submitted'.
    4. Records a ComplaintTimeline audit event.
    5. Commits transaction safely.
    """
    complaint = get_complaint_for_user(complaint_id, user_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")
    if complaint.status != 'draft':
        raise ValueError("This complaint has already been submitted.")

    # Validate mandatory fields
    validate_for_submission(complaint)

    # Transition status
    complaint.status = 'submitted'
    complaint.updated_at = datetime.utcnow()

    # Create submission timeline record
    timeline_entry = ComplaintTimeline(
        complaint_id=complaint.id,
        actor_user_id=user_id,
        event_type='complaint_submitted',
        previous_status='draft',
        new_status='submitted',
        message='Complaint submitted by citizen.',
        is_visible_to_user=True,
        created_at=datetime.utcnow()
    )
    db.session.add(timeline_entry)
    db.session.commit()
    return complaint


def validate_file_content(file_bytes, ext):
    """
    Validates magic bytes / header signatures for uploaded evidence.
    """
    if ext in ('.jpg', '.jpeg'):
        if not file_bytes.startswith(MAGIC_SIGNATURES['jpeg']):
            raise ValueError("File content does not match JPEG signature.")
    elif ext == '.png':
        if not file_bytes.startswith(MAGIC_SIGNATURES['png']):
            raise ValueError("File content does not match PNG signature.")
    elif ext == '.webp':
        if len(file_bytes) < 12 or not (file_bytes.startswith(b'RIFF') and file_bytes[8:12] == b'WEBP'):
            raise ValueError("File content does not match WebP signature.")
    elif ext == '.pdf':
        if not file_bytes.startswith(MAGIC_SIGNATURES['pdf']):
            raise ValueError("File content does not match PDF signature.")
    elif ext == '.ogg':
        if not file_bytes.startswith(MAGIC_SIGNATURES['ogg']):
            raise ValueError("File content does not match Ogg signature.")
    elif ext == '.webm':
        if not file_bytes.startswith(MAGIC_SIGNATURES['webm']):
            raise ValueError("File content does not match WebM signature.")
    elif ext == '.wav':
        if len(file_bytes) < 12 or not (file_bytes.startswith(b'RIFF') and file_bytes[8:12] == b'WAVE'):
            raise ValueError("File content does not match WAV signature.")
    elif ext in ('.mp4', '.m4a'):
        # MP4/M4A containers start with a 4-byte box size followed by 'ftyp' at bytes 4-8
        if len(file_bytes) < 12 or file_bytes[4:8] != b'ftyp':
            raise ValueError("File content does not match MP4/M4A audio signature.")


def determine_evidence_type(ext):
    """Classifies file extension into allowed evidence_type."""
    if ext in ALLOWED_EXTENSIONS['photo']:
        return 'photo'
    if ext in ALLOWED_EXTENSIONS['document']:
        return 'document'
    if ext in ALLOWED_EXTENSIONS['audio']:
        return 'audio'
    return 'other'


def attach_evidence_file(complaint_id, user_id, file_storage, custom_evidence_type=None, access_level='restricted', allow_supplementary=False):
    """
    Saves an uploaded evidence file into private case storage and registers metadata in SQL.
    Enforces file size limits, extension whitelist, magic bytes validation, and total case limits.
    Rolls back safely on failure: unlinks file if DB commit fails.
    """
    complaint = get_complaint_for_user(complaint_id, user_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")
    if not allow_supplementary and complaint.status != 'draft':
        raise ValueError("Cannot attach evidence to a submitted complaint.")

    if not file_storage or not file_storage.filename:
        raise ValueError("No file provided for upload.")

    orig_filename = secure_filename(file_storage.filename)
    if not orig_filename:
        orig_filename = "attachment"

    _, ext = os.path.splitext(orig_filename)
    ext = ext.lower()
    if ext not in ALL_ALLOWED_EXTS:
        raise ValueError(f"Unsupported file extension: '{ext}'. Allowed extensions: {sorted(list(ALL_ALLOWED_EXTS))}")

    # Read bytes into memory for validation & digest
    file_bytes = file_storage.read()
    file_size = len(file_bytes)
    if file_size == 0:
        raise ValueError("Uploaded file is empty.")

    # Size limit checks
    evidence_type = custom_evidence_type or determine_evidence_type(ext)
    if evidence_type in ('photo', 'document') and file_size > MAX_PHOTO_DOC_BYTES:
        raise ValueError(f"File size ({file_size / (1024*1024):.1f} MB) exceeds maximum 10 MB limit for photos/documents.")
    if evidence_type == 'audio' and file_size > MAX_AUDIO_BYTES:
        raise ValueError(f"Audio file size ({file_size / (1024*1024):.1f} MB) exceeds maximum 15 MB limit.")

    # Check total evidence size for this complaint
    current_total = db.session.query(db.func.coalesce(db.func.sum(ComplaintEvidence.file_size_bytes), 0))\
        .filter_by(complaint_id=complaint.id).scalar()
    if (current_total + file_size) > MAX_TOTAL_EVIDENCE_BYTES:
        raise ValueError(f"Total evidence for this complaint would exceed the 40 MB allowance (Current: {current_total / (1024*1024):.1f} MB).")

    # Content signature validation
    validate_file_content(file_bytes, ext)

    # Compute SHA-256 digest
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # Destination paths
    case_dir = get_complaint_storage_dir(complaint.complaint_number, create_subdirs=True)
    evidence_dir = os.path.join(case_dir, 'evidence')
    random_filename = f"{secrets.token_hex(16)}{ext}"
    target_abs_path = os.path.abspath(os.path.join(evidence_dir, random_filename))

    # Path traversal check
    if os.path.commonpath([evidence_dir, target_abs_path]) != evidence_dir:
        raise PermissionError("Path traversal rejected during evidence file write.")

    # Relative path stored in DB (case_storage/<complaint_number>/evidence/<random_filename>)
    relative_storage_path = os.path.join('case_storage', complaint.complaint_number, 'evidence', random_filename).replace('\\', '/')

    # Write file to disk
    try:
        with open(target_abs_path, 'wb') as f:
            f.write(file_bytes)
    except Exception as e:
        raise IOError(f"Failed to write evidence file to disk: {e}")

    try:
        # Register in DB with rollback safety
        mime = getattr(file_storage, 'mimetype', None) or 'application/octet-stream'
        evidence_record = ComplaintEvidence(
            complaint_id=complaint.id,
            uploaded_by_id=user_id,
            evidence_type=evidence_type,
            source_kind='uploaded',
            storage_path=relative_storage_path,
            original_filename=orig_filename,
            mime_type=mime,
            file_size_bytes=file_size,
            sha256_hex=sha256_hash,
            access_level=access_level,
            created_at=datetime.utcnow()
        )
        db.session.add(evidence_record)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Clean up unreferenced disk file on failure
        if os.path.isfile(target_abs_path):
            try:
                os.unlink(target_abs_path)
            except OSError:
                pass
        raise e

    return evidence_record


def remove_evidence_file(complaint_id, evidence_id, user_id):
    """
    Deletes an attached evidence record and its underlying disk file.
    Only allowed for drafts owned by the current user.
    """
    complaint = get_complaint_for_user(complaint_id, user_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")
    if complaint.status != 'draft':
        raise ValueError("Cannot remove evidence from a submitted complaint.")

    evidence = ComplaintEvidence.query.filter_by(id=evidence_id, complaint_id=complaint.id).first()
    if not evidence:
        raise ValueError(f"Evidence record {evidence_id} not found for this complaint.")

    # Resolve physical disk path
    root = get_case_storage_root()
    rel_path = evidence.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_path = os.path.abspath(os.path.join(root, rel_path))

    # Verify containment
    if os.path.commonpath([root, abs_path]) != root:
        raise PermissionError("Path traversal detected during evidence deletion.")

    # Delete record from database first with transaction-safe rollback
    try:
        db.session.delete(evidence)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

    # Unlink file only after DB deletion commits successfully
    if os.path.isfile(abs_path):
        try:
            os.unlink(abs_path)
        except OSError:
            pass

    return True


def delete_draft_complaint(complaint_id, user_id):
    """
    Safely deletes a citizen's draft complaint and all associated evidence files and timeline records.
    Enforces ownership and ensures submitted/active complaints cannot be deleted.
    """
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")
    if complaint.created_by_id != user_id:
        raise PermissionError("Unauthorized: You do not own this complaint.")
    if complaint.status != 'draft':
        raise ValueError(f"Submitted complaints ({complaint.complaint_number}) cannot be deleted.")

    complaint_number = complaint.complaint_number
    root = get_case_storage_root()
    case_dir = os.path.abspath(os.path.join(root, complaint_number))

    # 1. Gather all attached evidence files for physical removal
    evidence_records = ComplaintEvidence.query.filter_by(complaint_id=complaint.id).all()
    files_to_unlink = []
    for ev in evidence_records:
        if ev.storage_path:
            rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
            abs_path = os.path.abspath(os.path.join(root, rel))
            if os.path.commonpath([root, abs_path]) == root:
                files_to_unlink.append(abs_path)

    # 2. Database deletion in an atomic transaction
    try:
        # Delete evidence records first to satisfy FK constraints
        for ev in evidence_records:
            db.session.delete(ev)
        # Delete timeline entries
        ComplaintTimeline.query.filter_by(complaint_id=complaint.id).delete()
        # Delete complaint
        db.session.delete(complaint)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

    # 3. Clean up physical files and case directory only after DB commit succeeds
    for fpath in files_to_unlink:
        if os.path.isfile(fpath):
            try:
                os.unlink(fpath)
            except OSError:
                pass

    if os.path.isdir(case_dir) and os.path.commonpath([root, case_dir]) == root:
        try:
            import shutil
            shutil.rmtree(case_dir, ignore_errors=True)
        except Exception:
            pass

    return complaint_number
