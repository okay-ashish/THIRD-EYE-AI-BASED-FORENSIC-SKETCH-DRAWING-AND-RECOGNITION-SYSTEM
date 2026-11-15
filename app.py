import os
import time
import json
import base64
import uuid
import secrets
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify, abort
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.utils import secure_filename
from models import (
    db, User, Person, bcrypt, Complaint, ComplaintEvidence, ComplaintTimeline,
    ALLOWED_COMPLAINT_STATUSES, ALLOWED_FACIAL_REFERENCE_TYPES
)
from services.complaint_service import (
    create_draft_complaint,
    update_draft_complaint,
    submit_complaint,
    attach_evidence_file,
    remove_evidence_file,
    get_complaint_for_user,
    get_complaint_storage_dir,
    get_case_storage_root,
    ComplaintValidationError
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
    get_eligible_recognition_evidence,
    validate_recognition_source_evidence,
    ADMIN_PERMITTED_TRANSITIONS,
    USER_PERMITTED_TRANSITIONS,
    ACTIVE_INVESTIGATION_STATUSES
)
from utils import get_face_encoding, serialize_encoding, find_matches, convert_to_sketch_in_memory, process_photo_to_sketch
import cv2
from face_reconstruction import reconstruct_face, SKIN_TONE_PALETTE
from face_variations import generate_face_variations, extract_face_geometry
from poster_generator import generate_poster_pdf
from session_cleanup import (
    get_or_create_session_id,
    get_session_dir,
    cleanup_session_artifacts,
    cleanup_stale_sessions,
    cleanup_temp_file
)

import urllib.parse

# --- ENVIRONMENT CONFIGURATION ---
def _load_env_file():
    """Load configuration from .env file into environment if present."""
    if os.environ.get('THIRDEYE_IGNORE_DOTENV', '').lower() in ('true', '1'):
        return
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.isfile(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('"\'')
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_file()

# --- APP CONFIGURATION ---
from flask import Request
Request.max_form_memory_size = 50 * 1024 * 1024  # 50 MB limit for base64 sketches

app = Flask(__name__)

# Database and Security Configuration from Environment Variables
db_host = os.environ.get('THIRDEYE_DB_HOST', 'localhost')
db_port = os.environ.get('THIRDEYE_DB_PORT', '3306')
db_user = os.environ.get('THIRDEYE_DB_USER', 'root')
db_password = os.environ.get('THIRDEYE_DB_PASSWORD', '')
db_name = os.environ.get('THIRDEYE_DB_NAME', 'thirdeye_db')

if db_password:
    encoded_pw = urllib.parse.quote_plus(db_password)
    default_db_uri = f"mysql+mysqlconnector://{db_user}:{encoded_pw}@{db_host}:{db_port}/{db_name}"
else:
    default_db_uri = f"mysql+mysqlconnector://{db_user}@{db_host}:{db_port}/{db_name}"

# Secret Key Configuration (Hardened Environment-Specific Resolution)
raw_secret = os.environ.get('THIRDEYE_SECRET_KEY') or os.environ.get('SECRET_KEY')
if raw_secret:
    raw_secret = raw_secret.strip()

is_production = (
    os.environ.get('FLASK_ENV', '').lower() == 'production' or
    os.environ.get('ENV', '').lower() == 'production' or
    os.environ.get('THIRDEYE_ENV', '').lower() == 'production'
)

if is_production:
    if not raw_secret:
        raise RuntimeError(
            "FATAL: THIRDEYE_SECRET_KEY environment variable is required and must not be empty in production mode."
        )
    app.config['SECRET_KEY'] = raw_secret
else:
    if raw_secret:
        app.config['SECRET_KEY'] = raw_secret
    else:
        app.config['SECRET_KEY'] = secrets.token_hex(32)
        import warnings
        warnings.warn(
            "SECURITY WARNING: THIRDEYE_SECRET_KEY is not configured. Generated a temporary "
            "cryptographic key for development/testing. Sessions and CSRF tokens will be "
            "invalidated when the application restarts.",
            RuntimeWarning
        )

db_uri_env = os.environ.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL')
if db_uri_env:
    if db_uri_env.startswith('mysql://'):
        db_uri_env = db_uri_env.replace('mysql://', 'mysql+mysqlconnector://', 1)
    elif db_uri_env.startswith('postgres://'):
        db_uri_env = db_uri_env.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri_env
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = default_db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['MAX_FORM_MEMORY_SIZE'] = 50 * 1024 * 1024

# Session Security and Cookie Hardening (CSRF Baseline & Credential Protection)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = (
    is_production or
    os.environ.get('THIRDEYE_COOKIE_SECURE', 'false').lower() in ('true', '1')
)
app.config['UPLOAD_FOLDER'] = 'static/person_db'
app.config['SKETCH_UPLOAD_FOLDER'] = 'static/uploads'
app.config['GENERATED_FACES_FOLDER'] = 'static/generated_faces'
app.config['GENERATED_VARIATIONS_FOLDER'] = 'static/generated_variations'
app.config['GENERATED_POSTERS_FOLDER'] = 'static/generated_posters'
app.config['TEMP_UPLOAD_FOLDER'] = 'static/uploads'
app.config['TEMP_RETENTION_HOURS'] = 6

_last_cleanup_timestamp = 0

@app.before_request
def trigger_periodic_cleanup():
    global _last_cleanup_timestamp
    now = time.time()
    # Prune stale session directories every 30 minutes without extra daemon threads
    if now - _last_cleanup_timestamp > 1800:
        _last_cleanup_timestamp = now
        retention = app.config.get('TEMP_RETENTION_HOURS', 6)
        cleanup_stale_sessions(retention_hours=retention)

# --- INITIALIZE EXTENSIONS ---
db.init_app(app)
bcrypt.init_app(app)
csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.endswith(('/draft', '/evidence', '/submit', '/delete')):
        return jsonify({
            'success': False,
            'error': f'CSRF validation failed: {e.description}.',
            'code': 'CSRF_INVALID'
        }), 400
    flash(f'Security validation failed: {e.description}. Please refresh the page and try again.', 'danger')
    return render_template('layout.html', error_title='Security Validation Failed', error_message=f'CSRF validation failed: {e.description}. Please refresh the page and try again.'), 400

@app.errorhandler(404)
def handle_not_found(e):
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found', 'code': 404}), 404
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def handle_forbidden(e):
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return jsonify({'error': 'Access forbidden', 'code': 403}), 403
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def handle_server_error(e):
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error', 'code': 500}), 500
    return render_template('errors/500.html'), 500

@app.after_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(self), camera=(), microphone=()'
    return response

@app.context_processor
def inject_template_globals():
    utcnow = datetime.utcnow()
    return {
        'now': utcnow,
        'current_year': utcnow.year
    }

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

# --- DECORATORS for access control ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        if session.get('role') != 'user':
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Forbidden: Only citizen accounts may submit complaints.'}), 403
            flash('Only citizen user accounts may submit complaints.', 'danger')
            return ("Forbidden: Only citizen accounts may submit complaints.", 403)
        return f(*args, **kwargs)
    return decorated_function

# --- SETUP COMMAND ---
@app.cli.command("init-db")
def init_db_command():
    """Creates the database tables and provisions an admin if credentials are provided."""
    db.create_all()
    admin_user = os.environ.get('THIRDEYE_ADMIN_USER', 'admin')
    admin_pass = os.environ.get('THIRDEYE_ADMIN_PASSWORD')
    if not admin_pass:
        print("Database tables initialized.")
        print("Notice: Admin account not created because THIRDEYE_ADMIN_PASSWORD is not set.")
        print("To provision an admin, set THIRDEYE_ADMIN_PASSWORD or run: python create_admin.py")
        return
    if not User.query.filter_by(username=admin_user).first():
        new_admin = User(username=admin_user, password=admin_pass, role='admin', full_name='System Administrator')
        db.session.add(new_admin)
        db.session.commit()
        print(f'Initialized database and created admin user: {admin_user}')
    else:
        print(f'Database tables verified. Admin user {admin_user} already exists.')

# --- MAIN & AUTHENTICATION ROUTES ---
@app.route('/')
@app.route('/home')
def home():
    user_stats = None
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        user_stats = get_user_dashboard_stats(session['user_id'])
    return render_template('home.html', user_stats=user_stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            clean_name = user.full_name.strip() if (user.full_name and user.full_name.strip()) else None
            session['full_name'] = clean_name
            session['session_id'] = uuid.uuid4().hex[:16]
            flash(f'Welcome, {clean_name or user.username}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            password=password,
            role='user',
            full_name=full_name if full_name else None
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    if request.method != 'POST':
        flash('Logout must be performed via a secure POST request.', 'warning')
        return redirect(url_for('home'))
    session_id = session.get('session_id')
    if session_id:
        cleanup_session_artifacts(session_id)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/admin/dashboard')
@app.route('/admin/cases')
@admin_required
def admin_dashboard():
    stats = get_admin_dashboard_stats()
    query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()

    q_filter = Complaint.query
    if status_filter and status_filter in ALLOWED_COMPLAINT_STATUSES:
        q_filter = q_filter.filter_by(status=status_filter)
    if query:
        search_pattern = f"%{query}%"
        q_filter = q_filter.filter(
            db.or_(
                Complaint.complaint_number.ilike(search_pattern),
                Complaint.title.ilike(search_pattern),
                Complaint.category.ilike(search_pattern),
                Complaint.location_address.ilike(search_pattern),
                Complaint.narrative.ilike(search_pattern),
                Complaint.suspect_identifying_marks.ilike(search_pattern),
                Complaint.suspect_additional_details.ilike(search_pattern),
                Complaint.assigned_officer_name.ilike(search_pattern)
            )
        )
    complaints = q_filter.order_by(Complaint.created_at.desc()).all()
    persons = Person.query.all()
    return render_template(
        'admin_dashboard.html',
        complaints=complaints,
        stats=stats,
        persons=persons,
        selected_status=status_filter,
        query=query
    )


@app.route('/admin/cases/<int:complaint_id>/review')
@admin_required
def admin_case_review(complaint_id):
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)

    timeline = complaint.timeline.order_by(ComplaintTimeline.created_at.asc()).all()
    all_evidence = complaint.evidence.order_by(ComplaintEvidence.created_at.desc()).all()
    derived_artifacts = [e for e in all_evidence if e.source_kind == 'generated']

    return render_template(
        'admin_case_review.html',
        complaint=complaint,
        timeline=timeline,
        timeline_entries=timeline,
        evidence_list=all_evidence,
        derived_artifacts=derived_artifacts
    )


@app.route('/admin/cases/<int:complaint_id>/action', methods=['POST'])
@admin_required
def admin_case_action(complaint_id):
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)

    action = request.form.get('action') or request.form.get('action_type')
    if action == 'update_status':
        action = 'update_investigation'
    actor_id = session['user_id']

    try:
        if action == 'start_review':
            transition_case_status(complaint.id, actor_id, 'under_review')
            flash(f"Complaint {complaint.complaint_number} marked under preliminary review.", 'success')

        elif action == 'request_info':
            reason = (request.form.get('request_reason') or request.form.get('info_message') or '').strip()
            if not reason:
                flash("Please specify the additional information requested.", 'danger')
                return redirect(url_for('admin_case_review', complaint_id=complaint.id))
            transition_case_status(complaint.id, actor_id, 'information_requested', message=reason)
            flash(f"Information request dispatched to citizen for case {complaint.complaint_number}.", 'warning')

        elif action == 'approve':
            notes = request.form.get('approval_notes', '').strip() or None
            transition_case_status(complaint.id, actor_id, 'approved', message=notes)
            flash(f"Complaint {complaint.complaint_number} approved for formal forensic investigation.", 'success')

        elif action == 'reject':
            reason = request.form.get('rejection_reason', '').strip()
            if not reason:
                flash("Rejection requires a documented justification.", 'danger')
                return redirect(url_for('admin_case_review', complaint_id=complaint.id))
            transition_case_status(complaint.id, actor_id, 'rejected', message=reason)
            flash(f"Complaint {complaint.complaint_number} rejected.", 'danger')

        elif action == 'assign_officer':
            name = request.form.get('officer_name', '').strip()
            officer_id = request.form.get('officer_id', '').strip()
            station = request.form.get('station', '').strip()
            contact = request.form.get('contact', '').strip()
            assign_case_officer(complaint.id, actor_id, name, officer_id, station, contact)
            flash(f"Investigating Officer {name} assigned to case {complaint.complaint_number}.", 'success')

        elif action == 'update_investigation':
            new_status = request.form.get('new_status', '').strip()
            notes = (request.form.get('status_notes') or request.form.get('status_remarks') or '').strip() or None
            transition_case_status(complaint.id, actor_id, new_status, message=notes)
            flash(f"Investigation status updated to {new_status.replace('_', ' ').title()}.", 'success')

        else:
            flash(f"Unknown action '{action}'.", 'danger')

    except Exception as e:
        flash(f"Action failed: {str(e)}", 'danger')

    return redirect(url_for('admin_case_review', complaint_id=complaint.id))


@app.route('/cases/<int:complaint_id>/poster/<int:evidence_id>/approve', methods=['POST'])
@login_required
def approve_case_poster(complaint_id, evidence_id):
    if session.get('role') != 'admin':
        abort(403)
    try:
        approve_poster_for_distribution(complaint_id, evidence_id, session['user_id'])
        flash("Official case poster approved for public distribution.", 'success')
    except Exception as e:
        flash(f"Failed to approve poster: {e}", 'danger')
    return redirect(url_for('admin_case_review', complaint_id=complaint_id))

@app.route('/admin/add_person', methods=['POST'])
@admin_required
def add_person():
    name = request.form['name']
    details = request.form['person_details']
    if 'photo' not in request.files or request.files['photo'].filename == '':
        flash('No photo selected', 'danger')
        return redirect(url_for('admin_dashboard'))

    file = request.files['photo']
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    encoding = get_face_encoding(filepath)
    if encoding is None:
        os.remove(filepath)
        flash('Could not find a face in the uploaded image.', 'danger')
        return redirect(url_for('admin_dashboard'))

    serialized = serialize_encoding(encoding)
    new_person = Person(name=name, person_details=details, image_path=filename, face_encoding=serialized)
    db.session.add(new_person)
    db.session.commit()
    flash('Person added successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_person/<int:person_id>', methods=['GET', 'POST'])
@admin_required
def delete_person(person_id):
    if request.method != 'POST':
        flash('Record deletion must be submitted via POST confirmation.', 'warning')
        return redirect(url_for('admin_dashboard'))
    person = Person.query.get_or_404(person_id)
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], person.image_path))
    except FileNotFoundError:
        pass
    db.session.delete(person)
    db.session.commit()
    flash('Person deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

def _guard_standalone_route(tool_name):
    c_ref = request.args.get('complaint_id') or request.args.get('case_id') or request.form.get('complaint_id')
    if not c_ref:
        flash("Direct access to forensic tools is disabled. All operations must be initiated from an authorized, approved case workspace.", "warning")
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('my_complaints'))

    try:
        c_id = int(c_ref)
    except (ValueError, TypeError):
        flash("Invalid case reference provided.", "danger")
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('my_complaints'))

    try:
        complaint = get_case_for_user(c_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)

    if not complaint:
        abort(404)

    allowed, msg = can_access_tool(complaint, tool_name)
    if not allowed:
        flash(f"Stage policy violation: {msg}", "danger")
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    target_map = {
        'sketch': 'case_sketch',
        'reconstruct': 'case_reconstruct',
        'variations': 'case_variations',
        'recognition': 'case_recognition',
        'poster': 'case_poster'
    }
    target = target_map.get(tool_name, 'case_workspace')
    return redirect(url_for(target, complaint_id=complaint.id))


# --- PHASE 4: CASE WORKSPACE & CASE-LINKED FORENSIC ROUTES ---
@app.route('/cases/<int:complaint_id>/workspace')
@login_required
def case_workspace(complaint_id):
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)
    if not complaint:
        abort(404)

    tools = ['sketch', 'reconstruct', 'variations', 'recognition', 'poster']
    tool_access = {}
    for t in tools:
        allowed, msg = can_access_tool(complaint, t)
        tool_access[t] = {'allowed': allowed, 'message': msg}

    all_ev = complaint.evidence.order_by(ComplaintEvidence.created_at.desc()).all()
    uploaded_ev = [e for e in all_ev if e.source_kind == 'uploaded']
    derived_ev = [e for e in all_ev if e.source_kind == 'generated']

    has_sketch = any(e.evidence_type == 'sketch' for e in derived_ev)
    has_reconstruction = any(e.evidence_type == 'reconstructed_face' for e in derived_ev)
    has_variation = any(e.evidence_type in ('variation', 'face_variation') for e in derived_ev)
    has_poster = any(e.evidence_type == 'poster' for e in derived_ev)
    has_approved_poster = any(e.evidence_type == 'poster' and e.access_level == 'public_notice' for e in derived_ev)

    timeline_entries = complaint.timeline.order_by(ComplaintTimeline.created_at.asc()).all()

    return render_template(
        'case_workspace.html',
        complaint=complaint,
        tool_access=tool_access,
        uploaded_evidence=uploaded_ev,
        derived_artifacts=derived_ev,
        evidence_list=all_ev,
        has_sketch=has_sketch,
        has_reconstruction=has_reconstruction,
        has_variation=has_variation,
        has_variations=has_variation,
        has_poster=has_poster,
        has_approved_poster=has_approved_poster,
        timeline_entries=timeline_entries
    )


@app.route('/cases/<int:complaint_id>/sketch', methods=['GET', 'POST'])
@login_required
def case_sketch(complaint_id):
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)
    if not complaint:
        abort(404)

    allowed, msg = can_access_tool(complaint, 'sketch')
    if not allowed:
        flash(f"Stage policy violation: {msg}", 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    if request.method == 'POST':
        sketch_data = request.form.get('sketch_data')
        if not sketch_data and 'sketch' in request.files:
            f = request.files['sketch']
            if f and f.filename:
                sketch_data = f.read()

        if not sketch_data:
            flash('No sketch input provided.', 'danger')
            return redirect(url_for('case_sketch', complaint_id=complaint.id))

        raw_bytes = None
        if isinstance(sketch_data, str) and sketch_data.startswith('data:image'):
            header, encoded = sketch_data.split(',', 1)
            raw_bytes = base64.b64decode(encoded)
        elif isinstance(sketch_data, bytes):
            raw_bytes = sketch_data
        elif isinstance(sketch_data, str) and os.path.isfile(sketch_data):
            with open(sketch_data, 'rb') as sf:
                raw_bytes = sf.read()
        else:
            try:
                raw_bytes = base64.b64decode(sketch_data)
            except Exception:
                raw_bytes = sketch_data.encode('utf-8') if isinstance(sketch_data, str) else None

        if not raw_bytes:
            flash('Failed to decode sketch image data.', 'danger')
            return redirect(url_for('case_sketch', complaint_id=complaint.id))

        save_case_artifact(
            complaint_id=complaint.id,
            actor_id=session['user_id'],
            file_bytes=raw_bytes,
            filename='composite_sketch.png',
            evidence_type='sketch',
            generation_method='composite_layers'
        )
        flash('Composite sketch successfully registered as a derived case artifact.', 'success')
        if complaint.status == 'draft':
            return redirect(url_for('edit_complaint', complaint_id=complaint.id, step=4))
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    parts = {}
    base_path = 'static/sketch_parts'
    cat_order = ['head', 'hair', 'eyebrows', 'eyes', 'nose', 'lips', 'mustach', 'more']
    if os.path.exists(base_path):
        existing_cats = [c for c in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, c))]
        ordered_cats = [c for c in cat_order if c in existing_cats] + [c for c in existing_cats if c not in cat_order]
        for category in ordered_cats:
            cat_path = os.path.join(base_path, category)
            cat_files = sorted(os.listdir(cat_path), key=lambda x: (not x.split('.')[0].isdigit(), int(x.split('.')[0]) if x.split('.')[0].isdigit() else 999, x))
            parts[category] = [f"{category}/{f}" for f in cat_files]

    return render_template('sketch.html', parts=parts, skin_tones=SKIN_TONE_PALETTE, complaint=complaint)


@app.route('/api/cases/<int:complaint_id>/suspect-description', methods=['GET'])
@login_required
def api_get_suspect_description(complaint_id):
    """
    Returns the saved suspect physical description from Step 1 for a specific complaint.
    Strictly enforces user authorization (Citizen must own the case; Admin has full access).
    """
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        return jsonify({'success': False, 'error': 'Unauthorized to view this case.'}), 403
    if not complaint:
        return jsonify({'success': False, 'error': 'Complaint not found.'}), 404

    # Extract facial hair if specified in suspect_hair or notes
    facial_hair = None
    if complaint.suspect_hair:
        lower_hair = complaint.suspect_hair.lower()
        if any(term in lower_hair for term in ['beard', 'mustach', 'goatee', 'stubble', 'shaven', 'sideburn']):
            facial_hair = complaint.suspect_hair

    return jsonify({
        'success': True,
        'complaint_id': complaint.id,
        'complaint_number': complaint.complaint_number,
        'title': complaint.title,
        'category': complaint.category,
        'status': complaint.status,
        'suspect_gender': complaint.suspect_gender or 'Not provided',
        'suspect_approx_age': complaint.suspect_approx_age or 'Not provided',
        'suspect_height': complaint.suspect_height or 'Not provided',
        'suspect_build': complaint.suspect_build or 'Not provided',
        'suspect_complexion': complaint.suspect_complexion or 'Not provided',
        'suspect_hair': complaint.suspect_hair or 'Not provided',
        'suspect_facial_hair': facial_hair or 'Not provided',
        'suspect_eyes': complaint.suspect_eyes or 'Not provided',
        'suspect_nose': getattr(complaint, 'suspect_nose', None) or 'Not provided',
        'suspect_lips': getattr(complaint, 'suspect_lips', None) or 'Not provided',
        'suspect_mask_description': complaint.suspect_mask_description or 'Not provided',
        'suspect_identifying_marks': complaint.suspect_identifying_marks or 'Not provided',
        'suspect_clothing': complaint.suspect_clothing or 'Not provided',
        'suspect_accessories': complaint.suspect_accessories or 'Not provided',
        'suspect_additional_details': complaint.suspect_additional_details or 'Not provided'
    })


@app.route('/api/location/search', methods=['GET'])
@login_required
def api_location_search():
    """Search for locations or landmarks by query string."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': [], 'query': ''})
    limit = min(request.args.get('limit', 5, type=int), 10)
    from services.geocoding_service import search_locations
    results = search_locations(query, limit=limit)
    return jsonify({'query': query, 'results': results})


@app.route('/api/location/reverse', methods=['GET'])
@login_required
def api_location_reverse():
    """Reverse geocode latitude and longitude into a readable address."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'Missing lat or lon parameter'}), 400
    from services.geocoding_service import reverse_geocode
    res = reverse_geocode(lat, lon)
    return jsonify(res)


@app.route('/cases/<int:complaint_id>/reconstruct', methods=['GET', 'POST'])
@login_required
def case_reconstruct(complaint_id):
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)
    if not complaint:
        abort(404)

    allowed, msg = can_access_tool(complaint, 'reconstruct')
    if not allowed:
        flash(f"Stage policy violation: {msg}", 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    if request.method != 'POST':
        flash('Facial reconstruction generation requires POST request from case workspace.', 'info')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    sketch_ev = complaint.evidence.filter_by(source_kind='generated', evidence_type='sketch').order_by(ComplaintEvidence.created_at.desc()).first()
    if not sketch_ev:
        flash('A composite sketch must be constructed before facial reconstruction can proceed.', 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    root = get_case_storage_root()
    clean_rel = sketch_ev.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_sketch_path = os.path.abspath(os.path.join(root, clean_rel))

    if not os.path.isfile(abs_sketch_path):
        flash('Sketch file not found in case storage.', 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    skin_tone = request.form.get('skin_tone', 'medium')
    with open(abs_sketch_path, 'rb') as f:
        sketch_bytes = f.read()

    session_id = get_or_create_session_id()
    temp_dir = get_session_dir('faces', session_id)
    recon_res = reconstruct_face(sketch_bytes, output_dir=temp_dir, skin_tone=skin_tone)

    if recon_res and recon_res.get('success'):
        recon_path = os.path.join(temp_dir, recon_res['reconstruction_filename'])
        if os.path.isfile(recon_path):
            with open(recon_path, 'rb') as rf:
                recon_bytes = rf.read()
            save_case_artifact(
                complaint_id=complaint.id,
                actor_id=session['user_id'],
                file_bytes=recon_bytes,
                filename='reconstructed_face.png',
                evidence_type='reconstructed_face',
                generation_method='AI CycleGAN / ResNet-6 (AI-generated reconstruction; illustrative only, not a verified identity)',
                source_evidence_id=sketch_ev.id
            )
            flash('Sketch-to-face AI reconstruction generated. Notice: AI-generated reconstruction — illustrative only; not an actual photograph or verified identity.', 'success')
        else:
            flash('Failed to read reconstructed output image.', 'danger')
    else:
        flash('Facial reconstruction processing could not complete.', 'danger')

    return redirect(url_for('case_workspace', complaint_id=complaint.id))


@app.route('/cases/<int:complaint_id>/variations', methods=['GET', 'POST'])
@login_required
def case_variations(complaint_id):
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)
    if not complaint:
        abort(404)

    allowed, msg = can_access_tool(complaint, 'variations')
    if not allowed:
        flash(f"Stage policy violation: {msg}", 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    if request.method != 'POST':
        flash('Appearance variation generation requires POST request from case workspace.', 'info')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    root = get_case_storage_root()
    source_ev = None
    if complaint.facial_reference_type == 'photo_normal':
        source_ev = complaint.evidence.filter_by(source_kind='uploaded', evidence_type='photo').order_by(ComplaintEvidence.created_at.desc()).first()
    else:
        source_ev = complaint.evidence.filter_by(source_kind='generated', evidence_type='reconstructed_face').order_by(ComplaintEvidence.created_at.desc()).first()
        if not source_ev:
            source_ev = complaint.evidence.filter_by(source_kind='generated', evidence_type='sketch').order_by(ComplaintEvidence.created_at.desc()).first()

    if not source_ev:
        flash('No source image available to generate variations.', 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    clean_rel = source_ev.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_src_path = os.path.abspath(os.path.join(root, clean_rel))
    if not os.path.isfile(abs_src_path):
        flash('Source image file missing from storage.', 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    session_id = get_or_create_session_id()
    temp_dir = get_session_dir('variations', session_id)

    custom_settings = {
        'hair_style': request.form.get('hair_style', 'Short'),
        'facial_hair': request.form.get('facial_hair', 'Light Stubble'),
        'current_age': int(request.form.get('current_age', 30) or 30),
        'age_delta': int(request.form.get('age_delta', 5) or 5),
        'target_age': int(request.form.get('current_age', 30) or 30) + int(request.form.get('age_delta', 5) or 5),
        'headwear': request.form.get('headwear', 'None')
    }

    try:
        var_res = generate_face_variations(
            abs_src_path,
            output_dir=temp_dir,
            custom_settings=custom_settings,
            count=1,
            include_suggestions=False
        )
        pv = var_res.get('primary_variation')
        if pv:
            pv_path = os.path.join(temp_dir, os.path.basename(pv['filename']))
            if os.path.isfile(pv_path):
                with open(pv_path, 'rb') as vf:
                    var_bytes = vf.read()
                gen_method = 'Landmark Geometric Warping / Feature Synthesis'
                save_case_artifact(
                    complaint_id=complaint.id,
                    actor_id=session['user_id'],
                    file_bytes=var_bytes,
                    filename='appearance_variation.png',
                    evidence_type='variation',
                    generation_method=gen_method,
                    source_evidence_id=source_ev.id
                )
                flash('Appearance variation generated and registered to case dossier.', 'success')
            else:
                flash('Variation output file could not be read.', 'danger')
        else:
            flash('Variation generator did not produce an output image.', 'danger')
    except Exception as e:
        flash(f'Error generating variation: {e}', 'danger')

    return redirect(url_for('case_workspace', complaint_id=complaint.id))


@app.route('/cases/<int:complaint_id>/recognition', methods=['GET', 'POST'])
@login_required
def case_recognition(complaint_id):
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)
    if not complaint:
        abort(404)

    allowed, msg = can_access_tool(complaint, 'recognition')
    if not allowed:
        flash(f"Policy Enforcement: {msg}", 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    if complaint.facial_reference_type != 'photo_normal':
        flash("Biometric face recognition is restricted to Branch B cases with authentic unmasked photographic evidence.", 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    eligible_photos = get_eligible_recognition_evidence(complaint)
    if not eligible_photos:
        flash('Authentic photographic evidence is required for biometric recognition.', 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    # GET only displays the authorized case-bound recognition interface
    if request.method != 'POST':
        requested_ev_id = request.args.get('evidence_id')
        selected_evidence = None
        if requested_ev_id:
            try:
                selected_evidence = validate_recognition_source_evidence(complaint, requested_ev_id)
            except ValueError as ve:
                flash(f"Invalid recognition source evidence: {ve}", 'danger')
                return redirect(url_for('case_recognition', complaint_id=complaint.id))
        else:
            selected_evidence = eligible_photos[0]

        return render_template(
            'recognition.html',
            complaint=complaint,
            eligible_photos=eligible_photos,
            selected_evidence=selected_evidence,
            results=None,
            scan_executed=False,
            scan_error=None
        )

    # POST is strictly required to execute recognition
    requested_ev_id = request.form.get('evidence_id')
    if not requested_ev_id:
        flash("Source evidence ID is required to execute recognition.", "danger")
        return redirect(url_for('case_recognition', complaint_id=complaint.id))

    try:
        selected_evidence = validate_recognition_source_evidence(complaint, requested_ev_id)
    except ValueError as ve:
        flash(f"Invalid recognition source evidence: {ve}", 'danger')
        return redirect(url_for('case_recognition', complaint_id=complaint.id))

    root = get_case_storage_root()
    clean_rel = selected_evidence.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_photo_path = os.path.abspath(os.path.join(root, clean_rel))

    if os.path.commonpath([root, abs_photo_path]) != root or not os.path.isfile(abs_photo_path):
        flash('Source photographic evidence missing from secure case storage.', 'danger')
        return render_template(
            'recognition.html',
            complaint=complaint,
            eligible_photos=eligible_photos,
            selected_evidence=selected_evidence,
            results=[],
            scan_executed=True,
            scan_error="Source photographic evidence missing from secure case storage."
        )

    encoding = get_face_encoding(abs_photo_path)
    if encoding is not None:
        results = find_matches(encoding)
        timeline_entry = ComplaintTimeline(
            complaint_id=complaint.id,
            actor_user_id=session['user_id'],
            event_type='recognition_performed',
            previous_status=complaint.status,
            new_status=complaint.status,
            message=f"Biometric matching executed for evidence #{selected_evidence.id} ({selected_evidence.original_filename}) against Person DB ({len(results)} matches identified).",
            is_visible_to_user=True,
            created_at=datetime.utcnow()
        )
        db.session.add(timeline_entry)
        db.session.commit()
        if results:
            flash(f"Biometric recognition complete. Found {len(results)} candidate record match(es).", 'success')
        else:
            flash("Biometric encodings analyzed. No enrolled records exceeded similarity confidence threshold (50%).", 'info')
        return render_template(
            'recognition.html',
            complaint=complaint,
            eligible_photos=eligible_photos,
            selected_evidence=selected_evidence,
            results=results,
            scan_executed=True,
            scan_error=None
        )
    else:
        flash('No detectable face found in the authentic reference photo.', 'warning')
        return render_template(
            'recognition.html',
            complaint=complaint,
            eligible_photos=eligible_photos,
            selected_evidence=selected_evidence,
            results=[],
            scan_executed=True,
            scan_error="No detectable human face found in the authentic reference photograph. Check resolution, illumination, or head orientation."
        )


@app.route('/cases/<int:complaint_id>/poster', methods=['GET', 'POST'])
@login_required
def case_poster(complaint_id):
    try:
        complaint = get_case_for_user(complaint_id, session['user_id'], session.get('role'))
    except PermissionError:
        abort(403)
    if not complaint:
        abort(404)

    allowed, msg = can_access_tool(complaint, 'poster')
    if not allowed:
        flash(f"Stage policy violation: {msg}", 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    if request.method != 'POST':
        flash('Case poster generation requires POST request from case workspace.', 'info')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    root = get_case_storage_root()
    primary_ev = None
    if complaint.facial_reference_type == 'none':
        for t in ['variation', 'reconstructed_face', 'sketch']:
            primary_ev = complaint.evidence.filter_by(source_kind='generated', evidence_type=t).order_by(ComplaintEvidence.created_at.desc()).first()
            if primary_ev:
                break
    elif complaint.facial_reference_type == 'photo_normal':
        primary_ev = complaint.evidence.filter_by(source_kind='uploaded', evidence_type='photo').order_by(ComplaintEvidence.created_at.desc()).first()

    if not primary_ev:
        flash('An identifiable image is required before a poster draft can be created.', 'danger')
        return redirect(url_for('case_workspace', complaint_id=complaint.id))

    clean_rel = primary_ev.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_img_path = os.path.abspath(os.path.join(root, clean_rel))

    session_id = get_or_create_session_id()
    temp_dir = get_session_dir('posters', session_id)

    lbl = "LAST KNOWN PHOTOGRAPH" if primary_ev.source_kind == 'uploaded' else "COMPUTER-GENERATED RECONSTRUCTION"

    primary_face = {
        'image_path': abs_img_path,
        'source_type': 'real_photo' if primary_ev.source_kind == 'uploaded' else 'reconstructed',
        'label': lbl
    }

    person_data = {
        'full_name': 'UNIDENTIFIED SUBJECT',
        'gender': complaint.suspect_gender or 'Unknown',
        'age': str(complaint.suspect_approx_age or 'Unknown'),
        'case_number': complaint.complaint_number,
        'police_station': complaint.assigned_station or 'ThirdEye Investigation Division',
        'contact_person': complaint.assigned_officer_name or 'Investigating Authority',
        'phone': complaint.assigned_officer_contact or '+91 100 / +91 112',
        'location': complaint.location_address or 'Unspecified Location',
        'date_missing': complaint.incident_at.strftime('%d/%m/%Y') if complaint.incident_at else time.strftime('%d/%m/%Y'),
        'description': complaint.narrative or complaint.title or '',
        'custom_title': 'SUSPECT IDENTIFICATION NOTICE'
    }

    metadata = {
        'title': 'POLICE FORENSIC IDENTIFICATION NOTICE',
        'ref_no': complaint.complaint_number
    }

    res = generate_poster_pdf(
        primary_face=primary_face,
        addl_faces=[],
        template_id=1,
        person_data=person_data,
        metadata=metadata,
        orientation='portrait',
        output_dir=temp_dir
    )

    pdf_path = res['pdf_path']
    with open(pdf_path, 'rb') as pf:
        pdf_bytes = pf.read()

    save_case_artifact(
        complaint_id=complaint.id,
        actor_id=session['user_id'],
        file_bytes=pdf_bytes,
        filename=f"poster_{complaint.complaint_number}.pdf",
        evidence_type='poster',
        generation_method='ReportLab A4 Vector Publisher',
        source_evidence_id=primary_ev.id,
        access_level='internal'
    )

    flash('Poster draft generated and registered as an internal case artifact. Notice: Administrator approval is required before public distribution.', 'info')
    return redirect(url_for('case_workspace', complaint_id=complaint.id))


@app.route('/cases/<int:complaint_id>/poster/<int:evidence_id>/download')
@login_required
def download_case_poster(complaint_id, evidence_id):
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)

    ev = ComplaintEvidence.query.filter_by(id=evidence_id, complaint_id=complaint.id).first()
    if not ev or ev.evidence_type != 'poster':
        abort(404)

    if ev.access_level != 'public_notice':
        if session.get('role') != 'admin' and complaint.created_by_id != session.get('user_id'):
            abort(403)

    root = get_case_storage_root()
    clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_path = os.path.abspath(os.path.join(root, clean_rel))

    if os.path.commonpath([root, abs_path]) != root or not os.path.isfile(abs_path):
        abort(404)

    folder = os.path.dirname(abs_path)
    fname = os.path.basename(abs_path)
    return send_from_directory(folder, fname, as_attachment=True, download_name=ev.original_filename or f"poster_{complaint.complaint_number}.pdf")


@app.route('/public/cases/<int:complaint_id>/posters/<int:evidence_id>')
@app.route('/cases/<int:complaint_id>/poster/<int:evidence_id>/public-download')
def public_download_poster(complaint_id, evidence_id):
    """
    Public route for downloading authorized case posters.
    Strictly denied (HTTP 403) unless the poster has received explicit Admin approval (access_level == 'public_notice').
    """
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)

    ev = ComplaintEvidence.query.filter_by(id=evidence_id, complaint_id=complaint.id).first()
    if not ev or ev.evidence_type != 'poster':
        abort(404)

    if ev.access_level != 'public_notice':
        abort(403)

    root = get_case_storage_root()
    clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_path = os.path.abspath(os.path.join(root, clean_rel))

    if os.path.commonpath([root, abs_path]) != root or not os.path.isfile(abs_path):
        abort(404)

    folder = os.path.dirname(abs_path)
    fname = os.path.basename(abs_path)
    return send_from_directory(folder, fname, as_attachment=True, download_name=ev.original_filename or f"public_notice_{complaint.complaint_number}.pdf")


# --- STANDALONE TOOL COMPATIBILITY GUARDS ---
@app.route('/sketch')
@login_required
def sketch_constructor():
    return _guard_standalone_route('sketch')


@app.route('/recognition', methods=['GET', 'POST'])
@login_required
def recognition():
    return _guard_standalone_route('recognition')

# --- PHOTO TO SKETCH ROUTE (PHASE 5) ---
@app.route('/photo-to-sketch', methods=['GET', 'POST'])
@login_required
def photo_to_sketch():
    return _guard_standalone_route('photo_to_sketch')
    faces_dir = get_session_dir('faces', session_id)
    uploads_dir = get_session_dir('uploads', session_id)

    sketch_data_url = None
    orig_url = None
    sketch_url = None
    sketch_filename = None
    metrics = None
    orig_filename = None

    if request.method == 'POST':
        # 1. Validation: check if file was provided
        if 'photo' not in request.files:
            flash('No image selected.', 'danger')
            return render_template('photo_to_sketch.html')

        file = request.files['photo']
        if not file or file.filename == '':
            flash('No image selected.', 'danger')
            return render_template('photo_to_sketch.html')

        orig_filename = secure_filename(file.filename) or "reference_photo.jpg"
        ext = os.path.splitext(orig_filename)[1].lower()
        allowed_exts = {'.jpg', '.jpeg', '.png', '.webp'}
        if ext not in allowed_exts:
            flash('Unsupported image format. Allowed formats: JPG, PNG, WEBP.', 'danger')
            return render_template('photo_to_sketch.html')

        # 2. Check file size (max 16MB)
        file.seek(0, os.SEEK_END)
        size_bytes = file.tell()
        file.seek(0)
        if size_bytes > 16 * 1024 * 1024:
            flash('File size exceeds 16MB limit. Please upload a smaller image.', 'danger')
            return render_template('photo_to_sketch.html')

        # 3. Read image bytes
        image_bytes = file.read()
        if not image_bytes:
            flash('Unable to process this image. File is empty.', 'danger')
            return render_template('photo_to_sketch.html')

        # Optional controls (detail / contrast)
        ksize = request.form.get('ksize', 121)
        contrast = request.form.get('contrast', 1.0)
        try:
            ksize = int(ksize)
        except (ValueError, TypeError):
            ksize = 121
        try:
            contrast = float(contrast)
        except (ValueError, TypeError):
            contrast = 1.0

        # 4. Process conversion via OpenCV pipeline
        res = process_photo_to_sketch(image_bytes, ksize=ksize, contrast=contrast)
        if not res['success']:
            flash(res.get('error', 'Sketch conversion failed.'), 'danger')
            return render_template('photo_to_sketch.html')

        sketch_bytes = res['sketch_bytes']
        w, h = res['input_dims']
        proc_time = res['processing_time_ms']

        # 5. Session-scoped storage
        unique_token = uuid.uuid4().hex[:8]
        safe_orig_name = f"photo_{unique_token}{ext}"
        safe_orig_path = os.path.join(uploads_dir, safe_orig_name)
        with open(safe_orig_path, 'wb') as f_orig:
            f_orig.write(image_bytes)

        safe_sketch_name = f"sketch_photo_{unique_token}.jpg"
        safe_sketch_path = os.path.join(faces_dir, safe_sketch_name)
        with open(safe_sketch_path, 'wb') as f_sketch:
            f_sketch.write(sketch_bytes)

        # 6. Data URLs & relative URLs for display & handoff
        sketch_base64 = base64.b64encode(sketch_bytes).decode('utf-8')
        sketch_data_url = f"data:image/jpeg;base64,{sketch_base64}"
        orig_url = url_for('static', filename=f"uploads/temp_{session_id}/{safe_orig_name}")
        sketch_url = url_for('static', filename=f"generated_faces/session_{session_id}/{safe_sketch_name}")
        sketch_filename = f"session_{session_id}/{safe_sketch_name}"

        metrics = {
            'input_dims': f"{w} \u00d7 {h} px",
            'output_dims': f"{w} \u00d7 {h} px",
            'processing_time_ms': proc_time,
            'orig_filename': orig_filename,
            'ksize': ksize,
            'contrast': contrast
        }

    return render_template(
        'photo_to_sketch.html',
        sketch_data_url=sketch_data_url,
        orig_url=orig_url,
        sketch_url=sketch_url,
        sketch_filename=sketch_filename,
        metrics=metrics,
        orig_filename=orig_filename
    )


# --- CONSTRUCT FACE ROUTE (PHASE 2 & PHASE 3) ---
@app.route('/construct-face', methods=['GET', 'POST'])
@login_required
def construct_face():
    return _guard_standalone_route('reconstruct')
    session_faces_dir = get_session_dir('faces', session_id)

    if request.method == 'POST':
        sketch_data = request.form.get('sketch_data')
        skin_tone = request.form.get('skin_tone', 'medium')

        # Support saved sketch filename for regeneration
        if not sketch_data and request.form.get('sketch_filename'):
            saved_rel = request.form.get('sketch_filename')
            if saved_rel.startswith(f"session_{session_id}/"):
                saved_rel = saved_rel[len(f"session_{session_id}/"):]
            candidate_path = os.path.join(session_faces_dir, saved_rel)
            if os.path.exists(candidate_path):
                sketch_data = candidate_path

        # Also support multipart file upload if submitted as a file
        if not sketch_data and 'sketch' in request.files:
            file = request.files['sketch']
            if file and file.filename != '':
                sketch_data = file.read()

        if not sketch_data:
            flash('No sketch input provided for face construction.', 'danger')
            return redirect(url_for('sketch_constructor'))

        try:
            result = reconstruct_face(sketch_data, output_dir=session_faces_dir, skin_tone=skin_tone)
            if result.get('success'):
                # Prefix with session folder so template and downstream routes resolve session-scoped files
                result['sketch_filename'] = f"session_{session_id}/{result['sketch_filename']}"
                result['reconstruction_filename'] = f"session_{session_id}/{result['reconstruction_filename']}"
                return render_template('reconstructed_face.html', result=result, skin_tones=SKIN_TONE_PALETTE)
            else:
                flash('Face construction could not be completed.', 'danger')
                return redirect(url_for('sketch_constructor'))
        except Exception as e:
            flash(f'Error during face construction: {str(e)}', 'danger')
            return redirect(url_for('sketch_constructor'))

    # If accessed via GET, check if an existing reconstruction exists in session to view
    # Otherwise redirect to sketch constructor (returns 302 as expected by tests)
    if os.path.exists(session_faces_dir):
        reconstructions = [f for f in os.listdir(session_faces_dir) if f.startswith('reconstruction_') and f.endswith('.png')]
        sketches = [f for f in os.listdir(session_faces_dir) if f.startswith('sketch_') and f.endswith('.png')]
        if reconstructions and sketches:
            reconstructions.sort(key=lambda x: os.path.getmtime(os.path.join(session_faces_dir, x)), reverse=True)
            sketches.sort(key=lambda x: os.path.getmtime(os.path.join(session_faces_dir, x)), reverse=True)
            result = {
                'success': True,
                'sketch_filename': f"session_{session_id}/{sketches[0]}",
                'reconstruction_filename': f"session_{session_id}/{reconstructions[0]}",
                'processing_time': 0.8,
                'dimensions': [700, 550],
                'landmarks_detected': True,
                'detection_tier': 'session_cached',
                'skin_tone': 'medium',
                'skin_tone_name': SKIN_TONE_PALETTE['medium']['name'],
                'method': 'AI-Assisted Neural Synthesis (CycleGAN / ResNet-6)',
                'ai_model_status': 'AI Reconstruction Model Active (Session Cache)',
                'engine_used': 'learned_cyclegan'
            }
            return render_template('reconstructed_face.html', result=result, skin_tones=SKIN_TONE_PALETTE)

    # If accessed via GET without existing reconstruction, redirect to the sketch constructor
    return redirect(url_for('sketch_constructor'))


# --- CREATE FACE VARIATIONS ROUTE (PHASE 4.1 PHOTO INPUT & SINGLE OUTPUT) ---
@app.route('/create-variations', methods=['GET', 'POST'])
@app.route('/face_variations', methods=['GET', 'POST'])
@login_required
def create_variations():
    return _guard_standalone_route('variations')
    base_face_filename = None
    custom_settings = None

    # Discover any existing Phase 3.1 reconstructions in current session
    session_faces_dir = get_session_dir('faces', session_id)
    existing_reconstructions = []
    if os.path.exists(session_faces_dir):
        for f in sorted(os.listdir(session_faces_dir), key=lambda x: os.path.getmtime(os.path.join(session_faces_dir, x)), reverse=True):
            if f.startswith('reconstruction_') and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                fpath = os.path.join(session_faces_dir, f)
                try:
                    fimg = cv2.imread(fpath)
                    dims = f"{fimg.shape[1]} \u00d7 {fimg.shape[0]}" if fimg is not None else "Reconstructed Face"
                except Exception:
                    dims = "Reconstructed Face"
                existing_reconstructions.append({
                    'filename': f"session_{session_id}/{f}",
                    'path': fpath,
                    'url': url_for('static', filename=f"generated_faces/session_{session_id}/{f}"),
                    'name': f,
                    'dimensions': dims
                })

    base_face_path = None

    # Handle direct photo upload from form
    if request.method == 'POST' and ('uploaded_photo' in request.files or 'photo' in request.files or 'image_file' in request.files):
        photo_file = request.files.get('uploaded_photo') or request.files.get('photo') or request.files.get('image_file')
        if photo_file and photo_file.filename != '':
            session_up_dir = get_session_dir('uploads', session_id)
            safe_name = secure_filename(photo_file.filename) or "uploaded_photo.png"
            new_fname = f"photo_{uuid.uuid4().hex[:8]}_{safe_name}"
            save_dest = os.path.join(session_up_dir, new_fname)
            photo_file.save(save_dest)
            base_face_path = save_dest
            base_face_filename = f"uploads/temp_{session_id}/{new_fname}"

    if request.method == 'POST':
        if request.is_json:
            data = request.get_json() or {}
            if not base_face_filename:
                base_face_filename = data.get('base_face_filename')
            custom_settings = data
        else:
            if not base_face_filename:
                base_face_filename = request.form.get('base_face_filename')
            try:
                cur_age_val = int(request.form.get('current_age', 25) or 25)
            except (ValueError, TypeError):
                cur_age_val = 25
            try:
                age_delta_val = int(request.form.get('age_delta', 0) or 0)
            except (ValueError, TypeError):
                age_delta_val = 0
            custom_settings = {
                'hair_style': request.form.get('hair_style') or request.form.get('hair', 'Keep Original'),
                'facial_hair': request.form.get('facial_hair', 'Keep Original'),
                'current_age': cur_age_val,
                'age_delta': age_delta_val,
                'target_age': max(10, min(90, cur_age_val + age_delta_val)),
                'headwear': request.form.get('headwear', 'None')
            }
    else:
        # GET request with query parameter
        base_face_filename = request.args.get('base_face_filename')

    # Resolve base face path if not already established via direct file upload
    if not base_face_path and base_face_filename:
        candidates = [
            os.path.join(get_session_dir('uploads', session_id), os.path.basename(base_face_filename)),
            os.path.join(session_faces_dir, os.path.basename(base_face_filename)),
            os.path.join(app.config['GENERATED_FACES_FOLDER'], base_face_filename),
            os.path.join('static', base_face_filename),
            os.path.join(app.config['UPLOAD_FOLDER'], base_face_filename),
            base_face_filename
        ]
        for c in candidates:
            if os.path.exists(c) and os.path.isfile(c):
                base_face_path = os.path.abspath(c)
                break

    # If no base face specified, try existing reconstructions in session
    if not base_face_path and existing_reconstructions:
        base_face_path = existing_reconstructions[0]['path']
        base_face_filename = existing_reconstructions[0]['filename']

    # Fallback to permanent real photograph database
    if not base_face_path:
        pdb_dir = app.config['UPLOAD_FOLDER']
        if os.path.exists(pdb_dir):
            photos = [f for f in os.listdir(pdb_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            if photos:
                base_face_filename = f"person_db/{photos[0]}"
                base_face_path = os.path.join(pdb_dir, photos[0])

    # If still no base face, user can upload via the UI
    source_url = None
    source_dimensions = "N/A"
    source_filename = "No photo selected"
    face_detected = False
    face_status = "Awaiting photo input"

    if base_face_path and os.path.exists(base_face_path):
        source_filename = os.path.basename(base_face_path)
        try:
            src_bgr = cv2.imread(base_face_path)
            if src_bgr is not None:
                source_dimensions = f"{src_bgr.shape[1]} \u00d7 {src_bgr.shape[0]}"
                geom = extract_face_geometry(src_bgr)
                face_detected = (geom is not None)
                face_status = "Face Detected (Landmarks Aligned)" if face_detected else "No Face Detected"
        except Exception:
            pass

        try:
            rel_path = os.path.relpath(base_face_path, os.path.abspath('static')).replace('\\', '/')
            source_url = url_for('static', filename=rel_path)
        except Exception:
            source_url = None

    # NO AUTOMATIC GENERATION ON GET (Section 3, 5, 6)
    if request.method == 'GET':
        result = {
            'base_face_filename': base_face_filename or '',
            'source_url': source_url,
            'source_filename': source_filename,
            'source_dimensions': source_dimensions,
            'face_detected': face_detected,
            'face_status': face_status,
            'is_generated': False,
            'existing_reconstructions': existing_reconstructions,
            'config': {
                'hair_style': 'Keep Original',
                'facial_hair': 'Keep Original',
                'current_age': 25,
                'age_delta': 0,
                'target_age': 25,
                'headwear': 'None'
            }
        }
        return render_template('face_variations.html', result=result)

    # POST: USER EXPLICITLY CLICKED "GENERATE VARIATION"
    if not base_face_path or not os.path.exists(base_face_path):
        if request.is_json:
            return jsonify({'success': False, 'error': 'No base face photo available. Please upload a photo first.'}), 400
        flash('No base face found to create variations. Please upload a photo or select an existing reconstruction.', 'danger')
        return redirect(url_for('create_variations'))

    try:
        session_vars_dir = get_session_dir('variations', session_id)
        result = generate_face_variations(
            base_face_path,
            output_dir=session_vars_dir,
            custom_settings=custom_settings,
            count=1,
            include_suggestions=False
        )

        # Ensure single output only with proper session URLs
        if result.get('primary_variation'):
            pv = result['primary_variation']
            if not pv['filename'].startswith(f"session_{session_id}/"):
                pv['filename'] = f"session_{session_id}/{pv['filename']}"
            pv['url'] = url_for('static', filename=f"generated_variations/{pv['filename']}")
            result['variations'] = [pv]

        result['suggested_variations'] = []
        result['total_variations'] = 1
        result['base_face_filename'] = base_face_filename
        result['source_url'] = source_url
        result['source_filename'] = source_filename
        result['source_dimensions'] = source_dimensions
        result['face_detected'] = face_detected
        result['face_status'] = face_status
        result['is_generated'] = True
        result['config'] = custom_settings
        result['existing_reconstructions'] = existing_reconstructions

        if request.is_json or request.form.get('source_type') == 'upload' or 'application/json' in request.headers.get('Accept', ''):
            return jsonify({
                'success': True,
                'result': result,
                'primary_variation': result.get('primary_variation'),
                'total_variations': result.get('total_variations', 1)
            })

        return render_template('face_variations.html', result=result)
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(f'Error generating appearance variation: {str(e)}', 'danger')
        return redirect(url_for('create_variations', base_face_filename=base_face_filename))


# --- API ENDPOINT: UPLOAD VARIATION SOURCE PHOTO WITH INSTANT DETECTION ---
@app.route('/api/upload-variation-source', methods=['POST'])
@login_required
def api_upload_variation_source():
    if 'photo' not in request.files and 'uploaded_photo' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400
    file = request.files.get('photo') or request.files.get('uploaded_photo')
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected.'}), 400

    safe_name = secure_filename(file.filename) or "uploaded_photo.png"
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
        return jsonify({'success': False, 'error': 'Invalid image format. Please upload JPG or PNG.'}), 400

    session_id = get_or_create_session_id()
    temp_dir = get_session_dir('uploads', session_id)
    new_fname = f"photo_{uuid.uuid4().hex[:8]}_{safe_name}"
    filepath = os.path.join(temp_dir, new_fname)

    try:
        file.save(filepath)
        img = cv2.imread(filepath)
        if img is None:
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'success': False, 'error': 'Unable to decode image file.'}), 400

        h, w = img.shape[:2]
        geom = extract_face_geometry(img)
        face_detected = (geom is not None)
        face_status = "Face Detected (Landmarks Aligned)" if face_detected else "No Face Detected"

        rel_name = f"uploads/temp_{session_id}/{new_fname}"
        return jsonify({
            'success': True,
            'filename': rel_name,
            'original_name': file.filename,
            'url': url_for('static', filename=rel_name),
            'dimensions': f"{w} \u00d7 {h}",
            'width': w,
            'height': h,
            'face_detected': face_detected,
            'face_status': face_status
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to process image: {str(e)}'}), 500


# --- CREATE POSTER ROUTE (PHASE 4 REDESIGNED) ---
@app.route('/create-poster', methods=['GET', 'POST'])
@login_required
def create_poster():
    return _guard_standalone_route('poster')
    # Gather available images across project folders
    available_images = []

    # 1. Real photographs in person_db (Permanent)
    pdb_dir = app.config['UPLOAD_FOLDER']
    if os.path.exists(pdb_dir):
        for f in sorted(os.listdir(pdb_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                available_images.append({
                    'filename': f,
                    'image_path': f"static/person_db/{f}",
                    'source_type': 'real_photo',
                    'label': f"Real Photograph ({f})"
                })

    # 2. Uploaded photos in current user session
    session_up_dir = get_session_dir('uploads', session_id)
    if os.path.exists(session_up_dir):
        for f in sorted(os.listdir(session_up_dir), key=lambda x: os.path.getmtime(os.path.join(session_up_dir, x)), reverse=True)[:5]:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                available_images.append({
                    'filename': f,
                    'image_path': f"static/uploads/temp_{session_id}/{f}",
                    'source_type': 'real_photo' if not f.startswith('temp_sketch') else 'sketch',
                    'label': f"Uploaded Image ({f[:15]}..)"
                })

    # 3. Computer-generated reconstructed base faces in current user session
    session_rf_dir = get_session_dir('faces', session_id)
    if os.path.exists(session_rf_dir):
        for f in sorted(os.listdir(session_rf_dir), key=lambda x: os.path.getmtime(os.path.join(session_rf_dir, x)), reverse=True)[:5]:
            if f.startswith('reconstruction_') and f.lower().endswith('.png'):
                available_images.append({
                    'filename': f,
                    'image_path': f"static/generated_faces/session_{session_id}/{f}",
                    'source_type': 'reconstructed',
                    'label': "Computer-Generated Reconstruction"
                })

    # 4. Computer-generated appearance variations in current user session
    session_var_dir = get_session_dir('variations', session_id)
    if os.path.exists(session_var_dir):
        for f in sorted(os.listdir(session_var_dir), key=lambda x: os.path.getmtime(os.path.join(session_var_dir, x)), reverse=True)[:8]:
            if f.startswith('variation_') and f.lower().endswith('.png'):
                available_images.append({
                    'filename': f,
                    'image_path': f"static/generated_variations/session_{session_id}/{f}",
                    'source_type': 'variation',
                    'label': "Computer-Generated Appearance"
                })

    # Handle POST or direct navigation
    poster_type = request.form.get('poster_type', 'person_info')
    template_id = int(request.form.get('template_id', 1 if poster_type != 'missing_person' else 4))
    orientation = request.form.get('orientation', 'portrait')

    # Handle direct photo upload from the poster editor
    if 'uploaded_photo' in request.files:
        photo_file = request.files['uploaded_photo']
        if photo_file and photo_file.filename != '':
            sec_name = "upload_poster_" + secure_filename(photo_file.filename)
            save_path = os.path.join(session_up_dir, sec_name)
            photo_file.save(save_path)
            new_img = {
                'filename': sec_name,
                'image_path': f"static/uploads/temp_{session_id}/{sec_name}",
                'source_type': 'real_photo',
                'label': "Uploaded Real Photograph"
            }
            available_images.insert(0, new_img)

    # Person details dictionary
    person_data = {
        'full_name': request.form.get('full_name', 'RAMESH KUMAR'),
        'age': request.form.get('age', '34'),
        'current_age': request.form.get('current_age', '39'),
        'gender': request.form.get('gender', 'Male'),
        'phone': request.form.get('phone', '+91 98765 43210'),
        'alt_phone': request.form.get('alt_phone', '+91 91234 56789'),
        'height': request.form.get('height', '5 ft 10 in (178 cm)'),
        'build': request.form.get('build', 'Medium Athletic'),
        'hair': request.form.get('hair', 'Short Dark Brown'),
        'eyes': request.form.get('eyes', 'Dark Brown'),
        'clothing': request.form.get('clothing', 'Blue collared shirt, dark grey trousers, brown sandals'),
        'identifying_marks': request.form.get('identifying_marks', 'Deep scar over left eyebrow'),
        'location': request.form.get('location', 'T. Nagar Bus Terminus, Chennai'),
        'date_missing': request.form.get('date_missing', '15th October 2021'),
        'case_number': request.form.get('case_number', 'CR-2026-9041'),
        'police_station': request.form.get('police_station', 'R-4 Soundarapandianar Angadi PS, Chennai'),
        'contact_person': request.form.get('contact_person', 'Inspector K. Rajan / Family Liaison'),
        'description': request.form.get('description', 'Subject was last seen boarding a southbound bus. Speaks Tamil and English.'),
        'custom_title': request.form.get('custom_title', 'PERSON INFORMATION'),
        'poster_type': poster_type
    }

    # Handle incoming variation forwarding from Phase 3 (face_variations.html)
    selected_json = request.form.get('selected_variations_json')
    forwarded_variations = []
    if selected_json:
        try:
            forwarded_variations = json.loads(selected_json)
        except Exception:
            forwarded_variations = []

    # Handle single variation forwarded from Phase 4.1 or face_variations.html
    sel_var = request.form.get('selected_variation_filename')
    base_face = request.form.get('base_face_filename')
    base_face_candidate = None

    if base_face:
        bc_candidates = [
            os.path.join(session_up_dir, base_face),
            os.path.join(pdb_dir, base_face),
            os.path.join(session_rf_dir, base_face),
            os.path.join('static', 'person_db', base_face),
            os.path.join('static', base_face),
            base_face
        ]
        for bc in bc_candidates:
            if os.path.exists(bc) and os.path.isfile(bc):
                rel_bc = os.path.relpath(bc, os.path.abspath('.')).replace('\\', '/')
                is_real = 'person_db' in bc or 'upload' in bc
                base_face_candidate = {
                    'filename': os.path.basename(bc),
                    'image_path': rel_bc,
                    'source_type': 'real_photo' if is_real else 'reconstructed',
                    'label': 'LAST KNOWN REAL PHOTO' if is_real else 'BASE RECONSTRUCTION'
                }
                break

    if sel_var:
        candidates = [
            os.path.join(app.config['GENERATED_VARIATIONS_FOLDER'], sel_var),
            os.path.join('static', 'generated_variations', sel_var),
            os.path.join('static', sel_var),
            sel_var
        ]
        for vc in candidates:
            if os.path.exists(vc) and os.path.isfile(vc):
                rel_img = os.path.relpath(vc, os.path.abspath('.')).replace('\\', '/')
                forwarded_variations.insert(0, {
                    'filename': os.path.basename(vc),
                    'image_path': rel_img,
                    'source_type': 'variation',
                    'label': 'COMPUTER-GENERATED APPEARANCE'
                })
                break

    # If variation was forwarded and no explicit template provided, default to Template 2
    if (forwarded_variations or sel_var) and 'template_id' not in request.form:
        template_id = 2

    # Select Primary Image
    primary_path = request.form.get('primary_image_path')
    primary_face = None

    if primary_path and os.path.exists(primary_path):
        src_type = 'real_photo' if 'person_db' in primary_path or 'upload' in primary_path else 'reconstructed'
        primary_face = {
            'image_path': primary_path,
            'source_type': src_type,
            'label': 'LAST KNOWN PHOTOGRAPH' if src_type == 'real_photo' else 'BASE RECONSTRUCTION'
        }
    elif base_face_candidate:
        primary_face = base_face_candidate
    elif forwarded_variations:
        fv = forwarded_variations[0]
        primary_face = {
            'image_path': fv.get('image_path', ''),
            'source_type': 'variation',
            'label': fv.get('label', 'COMPUTER-GENERATED APPEARANCE')
        }
    elif available_images:
        primary_face = available_images[0]
    else:
        primary_face = {
            'image_path': 'static/person_db/trump.jpg',
            'source_type': 'real_photo',
            'label': 'PHOTOGRAPH'
        }

    # Select Additional Images (up to 4)
    addl_faces = []
    addl_paths = request.form.getlist('additional_images')
    if addl_paths:
        for p in addl_paths[:4]:
            if os.path.exists(p):
                addl_faces.append({
                    'image_path': p,
                    'source_type': 'variation' if 'variation' in p else 'real_photo',
                    'label': 'COMPUTER-GENERATED APPEARANCE' if 'variation' in p else 'ADDITIONAL PHOTO'
                })
    elif forwarded_variations:
        start_idx = 0 if base_face_candidate else 1
        for fv in forwarded_variations[start_idx:5]:
            addl_faces.append({
                'image_path': fv.get('image_path', ''),
                'source_type': 'variation',
                'label': fv.get('label', 'COMPUTER-GENERATED APPEARANCE')
            })
    else:
        # Default up to 4 variations from available images if template expects them
        for img in available_images:
            if img['image_path'] != primary_face['image_path']:
                addl_faces.append(img)
            if len(addl_faces) >= 4:
                break

    session_posters_dir = get_session_dir('posters', session_id)

    # If action is direct download
    if request.form.get('action') == 'download_pdf':
        res = generate_poster_pdf(
            primary_face,
            addl_faces=addl_faces,
            template_id=template_id,
            person_data=person_data,
            orientation=orientation,
            output_dir=session_posters_dir
        )
        res['pdf_filename'] = f"session_{session_id}/{res['pdf_filename']}"
        return redirect(url_for('download_poster', filename=res['pdf_filename']))

    # Generate initial PDF for the live preview
    try:
        pdf_result = generate_poster_pdf(
            primary_face,
            addl_faces=addl_faces,
            template_id=template_id,
            person_data=person_data,
            orientation=orientation,
            output_dir=session_posters_dir
        )
        if pdf_result:
            pdf_result['pdf_filename'] = f"session_{session_id}/{pdf_result['pdf_filename']}"
    except Exception as e:
        flash(f"Error generating initial poster PDF: {str(e)}", "danger")
        pdf_result = None

    return render_template('create_poster.html',
                           available_images=available_images,
                           primary_face=primary_face,
                           addl_faces=addl_faces,
                           template_id=template_id,
                           poster_type=poster_type,
                           orientation=orientation,
                           person_data=person_data,
                           pdf_result=pdf_result)


@app.route('/api/generate-poster', methods=['POST'])
@login_required
def api_generate_poster():
    data = request.get_json() or {}
    primary_face = data.get('primary_face') or {}
    addl_faces = data.get('addl_faces') or []
    template_id = int(data.get('template_id', 1))
    orientation = data.get('orientation', 'portrait')
    person_data = data.get('person_data') or {}
    metadata = data.get('metadata') or {}

    if not primary_face or not primary_face.get('image_path'):
        return jsonify({'success': False, 'error': 'Primary image is required.'}), 400

    try:
        session_id = get_or_create_session_id()
        session_posters_dir = get_session_dir('posters', session_id)
        res = generate_poster_pdf(
            primary_face,
            addl_faces=addl_faces,
            template_id=template_id,
            person_data=person_data,
            metadata=metadata,
            orientation=orientation,
            output_dir=session_posters_dir
        )
        res['pdf_filename'] = f"session_{session_id}/{res['pdf_filename']}"
        res['download_url'] = url_for('download_poster', filename=res['pdf_filename'])
        res['pdf_url'] = url_for('static', filename='generated_posters/' + res['pdf_filename'])
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-variations-from-photo', methods=['POST'])
@login_required
def api_generate_variations_from_photo():
    data = request.get_json() or {}
    image_path = data.get('image_path')
    if not image_path or not os.path.exists(image_path):
        return jsonify({'success': False, 'error': 'Image not found.'}), 400

    try:
        session_id = get_or_create_session_id()
        session_vars_dir = get_session_dir('variations', session_id)
        res = generate_face_variations(
            image_path,
            output_dir=session_vars_dir,
            count=4
        )
        # Format variations with complete session image_paths
        variations = []
        for v in res.get('variations', []):
            rel_name = f"session_{session_id}/{v['filename']}"
            variations.append({
                'filename': rel_name,
                'image_path': f"static/generated_variations/{rel_name}",
                'label': v.get('label', f"Variation {v['variation_number']}"),
                'source_type': 'probable',
                'summary': v.get('summary', '')
            })
        return jsonify({'success': True, 'variations': variations})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/download-poster/<path:filename>')
@login_required
def download_poster(filename):
    base_dir = os.path.abspath(app.config['GENERATED_POSTERS_FOLDER'])
    file_path = os.path.abspath(os.path.join(base_dir, filename))
    if not file_path.startswith(base_dir) or not os.path.exists(file_path):
        flash('Poster PDF file not found.', 'danger')
        return redirect(url_for('sketch_constructor'))
    folder = os.path.dirname(file_path)
    fname = os.path.basename(file_path)
    return send_from_directory(folder, fname, as_attachment=True)


# --- PHASE 3 & 4: COMPLAINT WORKFLOW ROUTES ---
@app.route('/my-complaints')
@app.route('/my_complaints')
@login_required
@user_required
def my_complaints():
    user_id = session['user_id']
    query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()

    q_filter = Complaint.query.filter_by(created_by_id=user_id)
    if status_filter == 'active':
        q_filter = q_filter.filter(Complaint.status.in_(ACTIVE_INVESTIGATION_STATUSES))
    elif status_filter and status_filter in ALLOWED_COMPLAINT_STATUSES:
        q_filter = q_filter.filter_by(status=status_filter)
    if query:
        search_pattern = f"%{query}%"
        q_filter = q_filter.filter(
            db.or_(
                Complaint.complaint_number.ilike(search_pattern),
                Complaint.title.ilike(search_pattern),
                Complaint.category.ilike(search_pattern),
                Complaint.location_address.ilike(search_pattern),
                Complaint.narrative.ilike(search_pattern),
                Complaint.suspect_identifying_marks.ilike(search_pattern),
                Complaint.suspect_additional_details.ilike(search_pattern)
            )
        )

    complaints = q_filter.order_by(Complaint.created_at.desc()).all()
    user_stats = get_user_dashboard_stats(user_id)
    return render_template(
        'my_complaints.html',
        complaints=complaints,
        status_counts=user_stats,
        query=query,
        selected_status=status_filter
    )


@app.route('/complaints/<int:complaint_id>/delete', methods=['POST'])
@login_required
@user_required
def delete_complaint(complaint_id):
    """
    Deletes an unsubmitted draft complaint owned by the current citizen.
    Submitted cases and active investigations are strictly protected.
    """
    user_id = session.get('user_id')
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Complaint record not found.'}), 404
        flash('Complaint record not found.', 'danger')
        return redirect(url_for('my_complaints'))

    if complaint.created_by_id != user_id:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Unauthorized: You do not own this complaint.'}), 403
        flash("Unauthorized: You cannot delete another citizen's complaint.", 'danger')
        return redirect(url_for('my_complaints'))

    if complaint.status != 'draft':
        msg = f"Submitted complaints ({complaint.complaint_number}) are legally registered and cannot be deleted by citizens. Please contact your investigating officer or station administration."
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 400
        flash(msg, 'warning')
        return redirect(url_for('my_complaints'))

    try:
        from services.complaint_service import delete_draft_complaint
        comp_num = delete_draft_complaint(complaint_id, user_id)
        success_msg = f"Draft complaint {comp_num} was permanently deleted."
        if request.is_json:
            return jsonify({'success': True, 'message': success_msg, 'complaint_number': comp_num})
        flash(success_msg, 'success')
    except Exception as e:
        err_msg = f"Failed to delete draft: {str(e)}"
        if request.is_json:
            return jsonify({'success': False, 'error': err_msg}), 400
        flash(err_msg, 'danger')

    return redirect(url_for('my_complaints'))


@app.route('/complaints/<int:complaint_id>/respond', methods=['GET', 'POST'])
@login_required
@user_required
def respond_information_request(complaint_id):
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)
    if complaint.status != 'information_requested':
        flash('This complaint does not currently require an information response.', 'info')
        return redirect(url_for('my_complaints'))

    last_info_request = (
        complaint.timeline.filter_by(event_type='information_requested')
        .order_by(ComplaintTimeline.created_at.desc())
        .first()
    )

    if request.method == 'POST':
        addendum_text = request.form.get('addendum_text', '').strip()
        if not addendum_text:
            flash('Response text cannot be empty.', 'danger')
            return render_template('complaint_respond.html', complaint=complaint, last_info_request=last_info_request)

        supp_files = request.files.getlist('supplementary_files')
        valid_files = [f for f in supp_files if f and f.filename]

        try:
            submit_case_addendum(
                complaint_id=complaint.id,
                user_id=session['user_id'],
                addendum_text=addendum_text,
                supplementary_files=valid_files
            )
            flash(f"Addendum response submitted for complaint {complaint.complaint_number}. Case has returned to review.", 'success')
            return redirect(url_for('my_complaints'))
        except Exception as e:
            flash(f"Error submitting addendum: {e}", 'danger')
            return render_template('complaint_respond.html', complaint=complaint, last_info_request=last_info_request)

    return render_template('complaint_respond.html', complaint=complaint, last_info_request=last_info_request)


@app.route('/complaints/new', methods=['GET', 'POST'])
@login_required
@user_required
def new_complaint():
    """Start or resume a citizen crime complaint draft."""
    existing_draft = Complaint.query.filter_by(
        created_by_id=session['user_id'],
        status='draft'
    ).order_by(Complaint.updated_at.desc()).first()

    # GET is strictly read-only: does not create a draft in the database
    if request.method == 'GET':
        if existing_draft and request.args.get('fresh') != '1':
            return redirect(url_for('edit_complaint', complaint_id=existing_draft.id))
        return render_template('home.html', user_stats=get_user_dashboard_stats(session['user_id']), prompt_new_complaint=True)

    # POST: CSRF-protected complaint draft creation
    complaint = create_draft_complaint(session['user_id'])
    return redirect(url_for('edit_complaint', complaint_id=complaint.id))


@app.route('/complaints/<int:complaint_id>/edit', methods=['GET'])
@login_required
@user_required
def edit_complaint(complaint_id):
    """Resume the multi-step complaint wizard for an existing draft."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)

    if complaint.status != 'draft':
        flash('This complaint has already been submitted and cannot be edited.', 'info')
        return redirect(url_for('complaint_confirmation', complaint_id=complaint.id))

    evidence_list = complaint.evidence.order_by(ComplaintEvidence.created_at.desc()).all()
    active_step = request.args.get('step', 1, type=int)
    if active_step < 1 or active_step > 5:
        active_step = 1
    return render_template('complaint_wizard.html', complaint=complaint, evidence_list=evidence_list, active_step=active_step)


@app.route('/complaints/<int:complaint_id>/draft', methods=['POST'])
@login_required
@user_required
def save_draft_step(complaint_id):
    """Save the current wizard step data into the draft complaint."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)
    if complaint.status != 'draft':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'error': 'Cannot edit a complaint that has already been submitted.'}), 400
        flash('This complaint has already been submitted and cannot be edited.', 'warning')
        return redirect(url_for('complaint_confirmation', complaint_id=complaint.id))

    try:
        form_data = request.get_json(silent=True) or request.form.to_dict()
        complaint = update_draft_complaint(complaint_id, session['user_id'], form_data)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'status': 'success', 'message': 'Draft saved successfully.', 'complaint_id': complaint.id})
        flash('Draft saved successfully.', 'success')
        return redirect(url_for('edit_complaint', complaint_id=complaint.id))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'error': str(e)}), 400
        flash(f'Error saving draft: {e}', 'danger')
        return redirect(url_for('edit_complaint', complaint_id=complaint_id))


@app.route('/complaints/<int:complaint_id>/evidence', methods=['POST'])
@login_required
@user_required
def upload_complaint_evidence(complaint_id):
    """Attach supporting evidence files to the citizen's draft complaint."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)
    if complaint.status != 'draft':
        return jsonify({'error': 'Cannot attach evidence to a submitted complaint.'}), 400

    try:
        files = request.files.getlist('evidence_files')
        if not files or all(f.filename == '' for f in files):
            single_f = request.files.get('file')
            if single_f and single_f.filename:
                files = [single_f]

        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No file selected for upload.'}), 400

        if len(files) > 5:
            return jsonify({'error': 'Maximum 5 files can be uploaded per operation.'}), 400

        newly_attached = []
        for f in files:
            if f.filename:
                ev = attach_evidence_file(complaint_id, session['user_id'], f)
                newly_attached.append(ev)

        all_ev = complaint.evidence.order_by(ComplaintEvidence.created_at.desc()).all()
        serialized = [{
            'id': e.id,
            'original_filename': e.original_filename,
            'evidence_type': e.evidence_type,
            'file_size_bytes': e.file_size_bytes,
            'sha256_hex': e.sha256_hex
        } for e in all_ev]

        return jsonify({'success': True, 'count': len(newly_attached), 'evidence': serialized})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/complaints/<int:complaint_id>/evidence/<int:evidence_id>/delete', methods=['POST'])
@login_required
@user_required
def delete_complaint_evidence(complaint_id, evidence_id):
    """Remove an attached evidence file from the draft."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)
    if complaint.status != 'draft':
        return jsonify({'error': 'Cannot remove evidence from a submitted complaint.'}), 400

    try:
        remove_evidence_file(complaint_id, evidence_id, session['user_id'])
        remaining = [{
            'id': e.id,
            'original_filename': e.original_filename,
            'evidence_type': e.evidence_type,
            'file_size_bytes': e.file_size_bytes,
            'sha256_hex': e.sha256_hex
        } for e in complaint.evidence.all()]
        return jsonify({'success': True, 'remaining_evidence': remaining})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/complaints/<int:complaint_id>/evidence/<int:evidence_id>/view', methods=['GET'])
@app.route('/cases/<int:complaint_id>/evidence/<int:evidence_id>/view', methods=['GET'])
@login_required
def view_complaint_evidence(complaint_id, evidence_id):
    """Safely stream private evidence file to its owner or admin without exposing filesystem paths."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)

    ev = ComplaintEvidence.query.filter_by(id=evidence_id, complaint_id=complaint.id).first()
    if not ev:
        abort(404)

    user_id = session.get('user_id')
    user_role = session.get('role')
    is_owner = (complaint.created_by_id == user_id)
    is_admin = (user_role == 'admin')
    is_public = (ev.access_level == 'public_notice')

    if not (is_admin or is_owner or is_public):
        abort(403)

    root = get_case_storage_root()
    clean_rel = ev.storage_path.replace('case_storage/', '').replace('\\', '/')
    abs_path = os.path.abspath(os.path.join(root, clean_rel))

    # Path traversal check & file existence
    if os.path.commonpath([root, abs_path]) != root or not os.path.isfile(abs_path):
        abort(404)

    return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))


@app.route('/complaints/<int:complaint_id>/submit', methods=['POST'])
@login_required
@user_required
def submit_complaint_route(complaint_id):
    """Validate and finalize complaint submission."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)
    if complaint.status != 'draft':
        if request.is_json:
            return jsonify({'error': 'This complaint has already been submitted and cannot be resubmitted.'}), 400
        flash('This complaint has already been submitted and cannot be resubmitted.', 'warning')
        return redirect(url_for('complaint_confirmation', complaint_id=complaint.id))

    try:
        form_data = request.get_json(silent=True) or request.form.to_dict()
        if form_data:
            update_draft_complaint(complaint_id, session['user_id'], form_data)

        complaint = submit_complaint(complaint_id, session['user_id'])

        if request.is_json:
            return jsonify({
                'status': 'success',
                'complaint_number': complaint.complaint_number,
                'redirect': url_for('complaint_confirmation', complaint_id=complaint.id)
            })

        flash(f'Complaint {complaint.complaint_number} submitted successfully!', 'success')
        return redirect(url_for('complaint_confirmation', complaint_id=complaint.id))
    except ComplaintValidationError as e:
        if request.is_json:
            return jsonify({'status': 'error', 'errors': e.errors}), 400
        for field, msg in e.errors.items():
            flash(f'{msg}', 'danger')
        return redirect(url_for('edit_complaint', complaint_id=complaint_id))
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 400
        flash(f'Submission failed: {e}', 'danger')
        return redirect(url_for('edit_complaint', complaint_id=complaint_id))


@app.route('/complaints/<int:complaint_id>/confirmation', methods=['GET'])
@login_required
@user_required
def complaint_confirmation(complaint_id):
    """Render post-submission confirmation screen with complaint reference."""
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        abort(404)
    if complaint.created_by_id != session['user_id']:
        abort(403)

    if complaint.status == 'draft':
        return redirect(url_for('edit_complaint', complaint_id=complaint.id))

    return render_template('complaint_confirmation.html', complaint=complaint)


# --- UTILITY ROUTE FOR SERVING FILES ---
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    for folder_key in ['UPLOAD_FOLDER', 'SKETCH_UPLOAD_FOLDER', 'GENERATED_FACES_FOLDER', 'GENERATED_VARIATIONS_FOLDER', 'GENERATED_POSTERS_FOLDER']:
        base = os.path.abspath(app.config[folder_key])
        target = os.path.abspath(os.path.join(base, filename))
        if target.startswith(base) and os.path.exists(target) and os.path.isfile(target):
            return send_from_directory(os.path.dirname(target), os.path.basename(target))
    return "File not found.", 404

if __name__ == '__main__':
    # Ensure all necessary upload directories exist when the app starts
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['SKETCH_UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['GENERATED_FACES_FOLDER'], exist_ok=True)
    os.makedirs(app.config['GENERATED_VARIATIONS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['GENERATED_POSTERS_FOLDER'], exist_ok=True)
    app.run(debug=True)
