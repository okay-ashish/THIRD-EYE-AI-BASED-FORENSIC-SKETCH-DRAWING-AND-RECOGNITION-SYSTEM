"""
ThirdEye Case Workflow Service Layer (Phase 4)
==============================================
Encapsulates state machine transitions, role-based authorization,
audited citizen addenda, officer assignment, and sequential forensic tool guards.

Strict guarantees:
1. Two roles only: 'user' and 'admin'.
2. Users see/act only on their own cases; Admins manage authorized cases.
3. Original submitted narrative and evidence remain completely immutable.
4. Information requests create audited addenda and new supplementary evidence items.
5. Sequential forensic workflows respect facial_reference_type branches (A, B).
6. Posters remain draft ('internal') until explicitly approved ('public_notice') by Admin.
7. Important actions logged in ComplaintTimeline.
"""

import os
import secrets
import hashlib
from datetime import datetime
from werkzeug.utils import secure_filename

from models import (
    db,
    Complaint,
    ComplaintEvidence,
    ComplaintTimeline,
    User,
    ALLOWED_COMPLAINT_STATUSES,
    ALLOWED_FACIAL_REFERENCE_TYPES
)
from services.complaint_service import (
    get_case_storage_root,
    get_complaint_storage_dir,
    attach_evidence_file
)

# Permitted state transitions by role
# Current Status -> Set of permitted Next Statuses
ADMIN_PERMITTED_TRANSITIONS = {
    'submitted': {'under_review', 'information_requested', 'approved', 'rejected'},
    'under_review': {'information_requested', 'approved', 'rejected'},
    'information_requested': {'under_review', 'approved', 'rejected'},
    'approved': {'assigned', 'investigation_in_progress'},
    'assigned': {'investigation_in_progress', 'closed'},
    'investigation_in_progress': {'awaiting_further_evidence', 'closed'},
    'awaiting_further_evidence': {'investigation_in_progress', 'closed'},
    'rejected': set(),
    'closed': set(),
    'draft': set(),  # Admin cannot edit citizen drafts
}

USER_PERMITTED_TRANSITIONS = {
    'draft': {'submitted'},
    'information_requested': {'under_review'},  # When submitting audited addendum
}

# Statuses where case forensic workspace is active and unlocked
ACTIVE_INVESTIGATION_STATUSES = {
    'approved',
    'assigned',
    'investigation_in_progress',
    'awaiting_further_evidence',
    'closed'  # Workspace remains viewable in closed cases
}


def can_transition(current_status, target_status, user_role):
    """
    Validates if a status transition is permitted for the given role.
    """
    if target_status not in ALLOWED_COMPLAINT_STATUSES:
        return False
    if current_status == target_status:
        return False

    if user_role == 'admin':
        return target_status in ADMIN_PERMITTED_TRANSITIONS.get(current_status, set())
    elif user_role == 'user':
        return target_status in USER_PERMITTED_TRANSITIONS.get(current_status, set())
    return False


def get_case_for_user(complaint_id, user_id, user_role):
    """
    Retrieves complaint ensuring proper authorization:
    - Admin: can access any complaint.
    - User: can only access complaint if created_by_id == user_id.
    Raises PermissionError if unauthorized, returns None if not found.
    """
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return None

    if user_role == 'admin':
        return complaint
    elif user_role == 'user':
        if complaint.created_by_id != user_id:
            raise PermissionError(f"User {user_id} is not authorized to access complaint {complaint_id}.")
        return complaint
    else:
        raise PermissionError(f"Invalid user role '{user_role}'.")


def transition_case_status(complaint_id, actor_id, new_status, message=None, is_visible_to_user=True):
    """
    Safely transitions a complaint's status with server-side validation and audit logging.
    """
    actor = User.query.get(actor_id)
    if not actor:
        raise ValueError(f"Actor user with ID {actor_id} not found.")

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")

    old_status = complaint.status

    if not can_transition(old_status, new_status, actor.role):
        raise ValueError(
            f"Transition from '{old_status}' to '{new_status}' is not permitted for role '{actor.role}'."
        )

    # Rejection requires a non-empty explanation
    if new_status == 'rejected' and (not message or not message.strip()):
        raise ValueError("A specific reason is required when rejecting a complaint.")

    complaint.status = new_status
    complaint.updated_at = datetime.utcnow()

    if new_status in ('closed', 'rejected'):
        complaint.closed_at = datetime.utcnow()

    # Determine event type
    event_type_map = {
        'under_review': 'review_started',
        'information_requested': 'information_requested',
        'approved': 'complaint_approved',
        'rejected': 'complaint_rejected',
        'assigned': 'officer_assigned',
        'investigation_in_progress': 'investigation_started',
        'awaiting_further_evidence': 'awaiting_evidence',
        'closed': 'case_closed',
    }
    event_type = event_type_map.get(new_status, 'status_changed')

    default_messages = {
        'review_started': 'Officer initiated preliminary review of complaint.',
        'information_requested': message or 'Additional information requested from citizen.',
        'complaint_approved': 'Complaint approved for formal forensic investigation.',
        'complaint_rejected': f"Complaint rejected: {message}",
        'investigation_started': 'Forensic investigation proceedings commenced.',
        'awaiting_evidence': 'Case investigation marked awaiting supplementary forensic evidence.',
        'case_closed': message or 'Case investigation closed and archived.',
    }

    final_msg = message if message else default_messages.get(event_type, f"Status updated to {new_status}")

    timeline_entry = ComplaintTimeline(
        complaint_id=complaint.id,
        actor_user_id=actor.id,
        event_type=event_type,
        previous_status=old_status,
        new_status=new_status,
        message=final_msg,
        is_visible_to_user=is_visible_to_user,
        created_at=datetime.utcnow()
    )

    db.session.add(timeline_entry)
    db.session.commit()
    return complaint


def assign_case_officer(complaint_id, actor_id, officer_name, officer_id, station, contact=None):
    """
    Assigns or updates investigating officer details.
    Permitted for Admins on approved/assigned/in_progress cases.
    """
    actor = User.query.get(actor_id)
    if not actor or actor.role != 'admin':
        raise PermissionError("Only administrators may assign investigating officers.")

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")

    if complaint.status not in ('approved', 'assigned', 'investigation_in_progress', 'awaiting_further_evidence'):
        raise ValueError(f"Cannot assign officer to a complaint in status '{complaint.status}'.")

    if not officer_name or not officer_name.strip():
        raise ValueError("Investigating officer name is required.")
    if not officer_id or not officer_id.strip():
        raise ValueError("Officer Badge/Staff ID is required.")
    if not station or not station.strip():
        raise ValueError("Police station / department is required.")

    old_status = complaint.status
    complaint.assigned_officer_name = officer_name.strip()
    complaint.assigned_officer_id = officer_id.strip()
    complaint.assigned_station = station.strip()
    complaint.assigned_officer_contact = contact.strip() if contact else None

    # If currently 'approved', advance to 'assigned'
    if complaint.status == 'approved':
        complaint.status = 'assigned'

    complaint.updated_at = datetime.utcnow()

    msg = f"Assigned to {officer_name.strip()} (ID: {officer_id.strip()}), {station.strip()}"
    if contact:
        msg += f" [Contact: {contact.strip()}]"

    timeline_entry = ComplaintTimeline(
        complaint_id=complaint.id,
        actor_user_id=actor.id,
        event_type='officer_assigned',
        previous_status=old_status,
        new_status=complaint.status,
        message=msg,
        is_visible_to_user=True,
        created_at=datetime.utcnow()
    )

    db.session.add(timeline_entry)
    db.session.commit()
    return complaint


def submit_case_addendum(complaint_id, user_id, addendum_text, supplementary_files=None):
    """
    Submits an audited citizen addendum in response to an information request:
    1. Verifies complaint ownership and status == 'information_requested'.
    2. Enforces non-empty addendum text.
    3. Preserves original submitted complaint narrative and evidence 100% intact.
    4. Attaches any supplementary evidence as new ComplaintEvidence records.
    5. Transitions case back to 'under_review'.
    6. Logs audit timeline entry visible to user and admin.
    """
    user = User.query.get(user_id)
    if not user or user.role != 'user':
        raise PermissionError("Only citizen users may submit an information request addendum.")

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")

    if complaint.created_by_id != user.id:
        raise PermissionError("You are not authorized to submit information for this case.")

    if complaint.status != 'information_requested':
        raise ValueError(
            f"Addendum submission is only allowed when status is 'information_requested'. Current status: '{complaint.status}'."
        )

    if not addendum_text or not addendum_text.strip():
        raise ValueError("Response text cannot be empty.")

    # 1. Attach any supplementary evidence files without modifying existing ones
    attached_records = []
    if supplementary_files:
        # Allow attaching by temporarily validating and storing
        for f in supplementary_files:
            if f and f.filename:
                ev = attach_evidence_file(
                    complaint_id=complaint.id,
                    user_id=user.id,
                    file_storage=f,
                    access_level='restricted',
                    allow_supplementary=True
                )
                attached_records.append(ev)

    # 2. Transition back to 'under_review'
    old_status = complaint.status
    complaint.status = 'under_review'
    complaint.updated_at = datetime.utcnow()

    msg = f"Citizen Addendum: {addendum_text.strip()}"
    if attached_records:
        msg += f" ({len(attached_records)} supplementary file(s) attached)"

    timeline_entry = ComplaintTimeline(
        complaint_id=complaint.id,
        actor_user_id=user.id,
        event_type='information_response',
        previous_status=old_status,
        new_status='under_review',
        message=msg,
        is_visible_to_user=True,
        created_at=datetime.utcnow()
    )

    db.session.add(timeline_entry)
    db.session.commit()
    return complaint


def can_access_tool(complaint, tool_name):
    """
    Server-side validation for forensic tools in the case workspace.
    Enforces branch prerequisites and prevents out-of-order execution:
    - Branch A ('none'):
      - sketch: allowed immediately once approved/active.
      - reconstruct: requires at least 1 sketch artifact.
      - variations: requires at least 1 reconstructed face or sketch.
      - poster: allowed once an image artifact exists.
      - recognition: NOT permitted on generated sketch/reconstruction.
    - Branch B ('photo_normal'):
      - photo_normal ground truth available.
      - sketch & reconstruct: bypassed by default (not required).
      - variations: allowed from photo.
      - recognition: allowed ONLY using original photo.
      - poster: allowed using photo or variation.
    """
    if complaint.status not in ACTIVE_INVESTIGATION_STATUSES:
        return False, f"Forensic workspace is not active for cases in status '{complaint.status}'."

    branch = complaint.facial_reference_type
    generated_ev = complaint.evidence.filter_by(source_kind='generated').all()
    uploaded_ev = complaint.evidence.filter_by(source_kind='uploaded').all()

    has_sketch = any(e.evidence_type == 'sketch' for e in generated_ev)
    has_reconstruction = any(e.evidence_type == 'reconstructed_face' for e in generated_ev)
    has_photo = any(e.evidence_type == 'photo' for e in uploaded_ev)

    if branch == 'none':  # Branch A
        if tool_name == 'sketch':
            return True, "Composite sketch constructor available."
        elif tool_name == 'reconstruct':
            if not has_sketch:
                return False, "A composite sketch must be constructed before facial reconstruction can proceed."
            return True, "Sketch-to-face reconstruction available."
        elif tool_name == 'variations':
            if not (has_reconstruction or has_sketch):
                return False, "A reconstructed face or sketch is required to generate appearance variations."
            return True, "Face appearance variations available."
        elif tool_name == 'recognition':
            return False, "Automated face recognition against enrolled criminal records is not permitted on synthetic sketches or AI reconstructions."
        elif tool_name == 'poster':
            if not (has_reconstruction or has_sketch or has_photo):
                return False, "An identifiable suspect image (sketch or reconstruction) is required to design a poster."
            return True, "Poster creator available."

    elif branch == 'photo_normal':  # Branch B
        if tool_name in ('sketch', 'reconstruct'):
            return False, "Sketch construction is bypassed because an authentic photographic reference is available."
        elif tool_name == 'variations':
            if not has_photo:
                return False, "Original photographic evidence is missing for variation generation."
            return True, "Variations available directly from reference photograph."
        elif tool_name == 'recognition':
            if not has_photo:
                return False, "Original reference photograph is required for biometric matching."
            return True, "Biometric recognition available against enrolled records."
        elif tool_name == 'poster':
            if not has_photo:
                return False, "Photograph required to generate poster."
            return True, "Poster creator available."

    return False, f"Tool '{tool_name}' is not permitted for branch '{branch}'."


def save_case_artifact(complaint_id, actor_id, file_bytes, filename, evidence_type, generation_method=None, source_evidence_id=None, access_level='restricted'):
    """
    Saves a derived forensic output into private case storage and registers it as ComplaintEvidence:
    - Stored under case_storage/<complaint_number>/generated/<filename>
    - Marked source_kind='generated'
    - Linked to source_evidence_id if derived from another item
    - Timeline event logged
    """
    actor = User.query.get(actor_id)
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")

    case_dir = get_complaint_storage_dir(complaint.complaint_number, create_subdirs=True)
    generated_dir = os.path.join(case_dir, 'generated')
    os.makedirs(generated_dir, exist_ok=True)

    # Normalize evidence_type to match ALLOWED_EVIDENCE_TYPES
    if evidence_type == 'face_variation':
        evidence_type = 'variation'

    _, ext = os.path.splitext(filename)
    clean_ext = ext.lower() or '.png'
    random_filename = f"{evidence_type}_{secrets.token_hex(12)}{clean_ext}"
    abs_dest = os.path.abspath(os.path.join(generated_dir, random_filename))

    if os.path.commonpath([generated_dir, abs_dest]) != generated_dir:
        raise PermissionError("Path traversal attempt in artifact saving.")

    with open(abs_dest, 'wb') as f:
        f.write(file_bytes)

    rel_path = os.path.join('case_storage', complaint.complaint_number, 'generated', random_filename).replace('\\', '/')
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    if clean_ext == '.png':
        mime_type = 'image/png'
    elif clean_ext in ('.jpg', '.jpeg'):
        mime_type = 'image/jpeg'
    elif clean_ext == '.pdf':
        mime_type = 'application/pdf'
    elif clean_ext == '.webp':
        mime_type = 'image/webp'
    else:
        mime_type = 'application/octet-stream'

    ev_record = ComplaintEvidence(
        complaint_id=complaint.id,
        uploaded_by_id=actor.id if actor else None,
        source_evidence_id=source_evidence_id,
        evidence_type=evidence_type,
        source_kind='generated',
        storage_path=rel_path,
        original_filename=filename,
        mime_type=mime_type,
        file_size_bytes=len(file_bytes),
        sha256_hex=sha256_hash,
        generation_method=generation_method,
        access_level=access_level,
        created_at=datetime.utcnow()
    )

    # Log timeline event
    timeline_entry = ComplaintTimeline(
        complaint_id=complaint.id,
        actor_user_id=actor.id if actor else None,
        event_type=f"artifact_generated_{evidence_type}",
        previous_status=complaint.status,
        new_status=complaint.status,
        message=f"Generated case artifact: {evidence_type} ({generation_method or 'Heuristic/Neural model'})",
        is_visible_to_user=True,
        created_at=datetime.utcnow()
    )

    try:
        db.session.add(ev_record)
        db.session.add(timeline_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if os.path.isfile(abs_dest):
            try:
                os.unlink(abs_dest)
            except OSError:
                pass
        raise e

    return ev_record


def approve_poster_for_distribution(complaint_id, evidence_id, admin_id):
    """
    Explicitly approves a generated poster draft for public notice distribution:
    - Changes access_level from 'internal' to 'public_notice'
    - Admin authorization required
    - Logs audit timeline entry
    """
    admin = User.query.get(admin_id)
    if not admin or admin.role != 'admin':
        raise PermissionError("Only administrators may approve posters for public notice distribution.")

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint {complaint_id} not found.")

    evidence = ComplaintEvidence.query.filter_by(id=evidence_id, complaint_id=complaint.id).first()
    if not evidence or evidence.evidence_type != 'poster':
        raise ValueError(f"Poster artifact {evidence_id} not found on complaint {complaint_id}.")

    evidence.access_level = 'public_notice'
    evidence.updated_at = datetime.utcnow() if hasattr(evidence, 'updated_at') else None

    timeline_entry = ComplaintTimeline(
        complaint_id=complaint.id,
        actor_user_id=admin.id,
        event_type='poster_approved',
        previous_status=complaint.status,
        new_status=complaint.status,
        message=f"Official case poster ({evidence.original_filename or 'Notice'}) approved for public distribution.",
        is_visible_to_user=True,
        created_at=datetime.utcnow()
    )

    db.session.add(timeline_entry)
    db.session.commit()
    return evidence


def get_admin_dashboard_stats():
    """
    Returns real, database-backed case statistics and visualization metrics
    for the Officer / Admin dashboard.
    """
    all_complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    total = len(all_complaints)

    counts_by_status = {}
    for st in ALLOWED_COMPLAINT_STATUSES:
        counts_by_status[st] = 0

    counts_by_category = {}
    timeline_by_month = {}

    for c in all_complaints:
        counts_by_status[c.status] = counts_by_status.get(c.status, 0) + 1

        # Group by case category
        cat = (c.category or 'Uncategorized').strip()
        counts_by_category[cat] = counts_by_category.get(cat, 0) + 1

        # Group by creation month
        if c.created_at:
            m_key = c.created_at.strftime('%Y-%m')
            m_label = c.created_at.strftime('%b %Y')
            if m_key not in timeline_by_month:
                timeline_by_month[m_key] = {'label': m_label, 'count': 0}
            timeline_by_month[m_key]['count'] += 1

    awaiting_review = counts_by_status.get('submitted', 0)
    under_review = counts_by_status.get('under_review', 0)
    info_pending = counts_by_status.get('information_requested', 0)
    approved_assigned = counts_by_status.get('approved', 0) + counts_by_status.get('assigned', 0)
    in_progress = counts_by_status.get('investigation_in_progress', 0) + counts_by_status.get('awaiting_further_evidence', 0)
    closed_cases = counts_by_status.get('closed', 0)
    rejected_cases = counts_by_status.get('rejected', 0)

    # Status distribution chart (Teal, Lime, Warning, Success, Dark Muted, Error)
    status_chart = {
        'labels': ['Submitted', 'Under Review', 'Info Requested', 'Active Investigation', 'Closed', 'Rejected'],
        'data': [
            awaiting_review,
            under_review,
            info_pending,
            approved_assigned + in_progress,
            closed_cases,
            rejected_cases
        ],
        'colors': ['#43B7A7', '#B8E36A', '#F0BE62', '#69C78B', '#A0B0B6', '#F07878']
    }

    # Top categories chart
    sorted_cats = sorted(counts_by_category.items(), key=lambda x: x[1], reverse=True)[:6]
    category_palette = ['#43B7A7', '#B8E36A', '#69C78B', '#F0BE62', '#F07878', '#A0B0B6']
    category_chart = {
        'labels': [k for k, v in sorted_cats] if sorted_cats else [],
        'data': [v for k, v in sorted_cats] if sorted_cats else [],
        'colors': category_palette[:len(sorted_cats)] if sorted_cats else []
    }

    # Monthly cases activity timeline
    sorted_months = sorted(timeline_by_month.items(), key=lambda x: x[0])[-6:]
    timeline_chart = {
        'labels': [v['label'] for k, v in sorted_months] if sorted_months else [],
        'data': [v['count'] for k, v in sorted_months] if sorted_months else []
    }

    # Recent activity timeline events
    recent_events = (
        ComplaintTimeline.query
        .order_by(ComplaintTimeline.created_at.desc())
        .limit(6)
        .all()
    )

    return {
        'total': total,
        'by_status': counts_by_status,
        'awaiting_review': awaiting_review,
        'under_review': under_review,
        'info_pending': info_pending,
        'approved_assigned': approved_assigned,
        'in_progress': in_progress,
        'closed': closed_cases,
        'rejected': rejected_cases,
        'status_chart': status_chart,
        'category_chart': category_chart,
        'timeline_chart': timeline_chart,
        'recent_events': recent_events
    }


def get_user_dashboard_stats(user_id):
    """
    Returns real, database-backed case statistics and visualizations
    for an individual citizen's dashboard.
    """
    user_complaints = Complaint.query.filter_by(created_by_id=user_id).order_by(Complaint.created_at.desc()).all()
    total = len(user_complaints)

    drafts = [c for c in user_complaints if c.status == 'draft']
    under_review = [c for c in user_complaints if c.status in ('submitted', 'under_review')]
    info_needed = [c for c in user_complaints if c.status == 'information_requested']
    active_cases = [c for c in user_complaints if c.status in ACTIVE_INVESTIGATION_STATUSES]
    closed_rejected = [c for c in user_complaints if c.status in ('closed', 'rejected')]

    latest_draft = drafts[0] if drafts else None

    # Status distribution for user's reports
    user_status_chart = {
        'labels': ['Drafts', 'Under Review', 'Action Needed', 'Active Investigation', 'Closed / Resolved'],
        'data': [len(drafts), len(under_review), len(info_needed), len(active_cases), len(closed_rejected)],
        'colors': ['#A0B0B6', '#B8E36A', '#F0BE62', '#69C78B', '#43B7A7']
    }

    # Monthly activity for user
    monthly_counts = {}
    for c in user_complaints:
        if c.created_at:
            m_key = c.created_at.strftime('%Y-%m')
            m_label = c.created_at.strftime('%b %Y')
            if m_key not in monthly_counts:
                monthly_counts[m_key] = {'label': m_label, 'count': 0}
            monthly_counts[m_key]['count'] += 1

    sorted_user_months = sorted(monthly_counts.items(), key=lambda x: x[0])[-5:]
    user_timeline_chart = {
        'labels': [v['label'] for k, v in sorted_user_months] if sorted_user_months else [],
        'data': [v['count'] for k, v in sorted_user_months] if sorted_user_months else []
    }

    return {
        'total': total,
        'draft_count': len(drafts),
        'under_review_count': len(under_review),
        'info_needed_count': len(info_needed),
        'active_cases_count': len(active_cases),
        'closed_count': len(closed_rejected),
        'latest_draft': latest_draft,
        'complaints': user_complaints[:10],  # Latest 10 for dashboard display
        'status_chart': user_status_chart,
        'timeline_chart': user_timeline_chart
    }


def get_eligible_recognition_evidence(complaint):
    """
    Returns list of eligible source photographic evidence for biometric recognition.
    Strictly filters for:
    - Belongs to this complaint
    - Complaint is Branch B ('photo_normal')
    - source_kind == 'uploaded'
    - evidence_type == 'photo'
    """
    if not complaint or complaint.facial_reference_type != 'photo_normal':
        return []
    return complaint.evidence.filter_by(
        source_kind='uploaded',
        evidence_type='photo'
    ).order_by(ComplaintEvidence.created_at.asc()).all()


def validate_recognition_source_evidence(complaint, evidence_id):
    """
    Validates that the specified evidence_id:
    1. Belongs to the given complaint
    2. Is an authentic uploaded photograph (source_kind == 'uploaded', evidence_type == 'photo')
    3. The complaint is Branch B ('photo_normal')
    Returns the ComplaintEvidence instance if valid, otherwise raises ValueError.
    """
    if not complaint:
        raise ValueError("Invalid case reference.")

    if complaint.facial_reference_type != 'photo_normal':
        raise ValueError("Biometric recognition is strictly prohibited on non-Branch-B cases.")

    try:
        ev_id_int = int(evidence_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid evidence ID format: '{evidence_id}'.")

    evidence = ComplaintEvidence.query.filter_by(
        id=ev_id_int,
        complaint_id=complaint.id
    ).first()

    if not evidence:
        raise ValueError(f"Evidence artifact #{ev_id_int} does not belong to case {complaint.complaint_number}.")

    if evidence.source_kind != 'uploaded' or evidence.evidence_type != 'photo':
        raise ValueError("Only authentic uploaded photographs may be used for biometric recognition. Derived artifacts (sketches, reconstructions, variations) are strictly prohibited.")

    return evidence

