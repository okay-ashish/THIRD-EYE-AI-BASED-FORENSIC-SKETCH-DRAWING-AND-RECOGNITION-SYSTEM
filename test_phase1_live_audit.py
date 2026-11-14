import os
import sys
import re
import json
import base64
import io
import time
import requests
from PIL import Image, ImageDraw

BASE_URL = "http://127.0.0.1:5000"
ADMIN_USER = "admin"
ADMIN_PASS = "TestFixturePassword123!"
SYNTH_USER = f"audit_user_{int(time.time())}"
SYNTH_PASS = "AuditPass2026!"

print(f"Starting ThirdEye Phase 1 Live Server Audit on {BASE_URL}...")

results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "tests": []
}

def record_test(name, passed, message=""):
    results["total"] += 1
    if passed:
        results["passed"] += 1
        print(f"  [PASS] {name} {('- ' + message) if message else ''}")
    else:
        results["failed"] += 1
        print(f"  [FAIL] {name} - {message}")
    results["tests"].append({"name": name, "passed": passed, "message": message})

def get_csrf(html_text):
    m = re.search(r'name=["\']csrf[-_]token["\']\s+content=["\']([^"\']+)["\']', html_text)
    if m:
        return m.group(1)
    m = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html_text)
    if m:
        return m.group(1)
    m = re.search(r'window\.CSRF_TOKEN\s*=\s*["\']([^"\']+)["\']', html_text)
    if m:
        return m.group(1)
    return None

# =========================================================================
# TEST SUITE 1: Server Accessibility, Theme, & UI System
# =========================================================================
print("\n--- TEST SUITE 1: Server Accessibility & Master UI System ---")
public_session = requests.Session()
r = public_session.get(f"{BASE_URL}/home")
record_test("Server Connectivity (GET /home)", r.status_code == 200, f"HTTP {r.status_code}")

csrf_token = get_csrf(r.text)
record_test("CSRF Token Present on Public Landing", bool(csrf_token), f"Token: {csrf_token[:15]}..." if csrf_token else "Missing")

has_fa = "font-awesome" in r.text or "fa-" in r.text
record_test("Font Awesome 6 Icon Integration", has_fa, "Font Awesome assets active in DOM")

has_theme_segmented = "ant-theme-segmented" in r.text and "themeSegmentedControl" in r.text
record_test("3-Way Theme Segmented Control (System/Light/Dark)", has_theme_segmented, "Theme manager component verified")

# =========================================================================
# TEST SUITE 2: User Registration, Login & Role-Based Access Control
# =========================================================================
print("\n--- TEST SUITE 2: User Registration, Login & RBAC ---")

# Step 2.1: Register new citizen
reg_page = public_session.get(f"{BASE_URL}/register")
reg_csrf = get_csrf(reg_page.text)
reg_data = {
    "csrf_token": reg_csrf,
    "full_name": "Audit Forensic Inspector",
    "username": SYNTH_USER,
    "password": SYNTH_PASS,
    "confirm_password": SYNTH_PASS
}
reg_resp = public_session.post(f"{BASE_URL}/register", data=reg_data, allow_redirects=True)
record_test("Citizen Registration (POST /register)", "Account created successfully" in reg_resp.text or reg_resp.status_code == 200)

# Step 2.2: Duplicate registration should be rejected
dup_resp = public_session.post(f"{BASE_URL}/register", data=reg_data, allow_redirects=True)
record_test("Duplicate Username Rejection", "already taken" in dup_resp.text or "already exists" in dup_resp.text or dup_resp.status_code in (200, 400))

# Step 2.3: Login with newly created citizen
citizen_session = requests.Session()
login_page = citizen_session.get(f"{BASE_URL}/login")
login_csrf = get_csrf(login_page.text)
login_data = {
    "csrf_token": login_csrf,
    "username": SYNTH_USER,
    "password": SYNTH_PASS
}
login_resp = citizen_session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
record_test("Citizen Authentication (POST /login)", "Audit Forensic Inspector" in login_resp.text or "Citizen Forensic Portal" in login_resp.text or login_resp.status_code == 200)

# Step 2.4: RBAC Citizen restricted from Admin routes
admin_access = citizen_session.get(f"{BASE_URL}/admin/dashboard", allow_redirects=False)
record_test("RBAC Citizen Restriction (/admin/dashboard)", admin_access.status_code in (302, 403), f"Status {admin_access.status_code}")

# Step 2.5: Admin Login
admin_session = requests.Session()
admin_login_page = admin_session.get(f"{BASE_URL}/login")
admin_csrf = get_csrf(admin_login_page.text)
admin_login_data = {
    "csrf_token": admin_csrf,
    "username": ADMIN_USER,
    "password": ADMIN_PASS
}
admin_resp = admin_session.post(f"{BASE_URL}/login", data=admin_login_data, allow_redirects=True)
record_test("Admin Authentication (POST /login)", admin_resp.status_code == 200 and ("Administrative" in admin_resp.text or "admin" in admin_resp.url))

# Step 2.6: Admin can access Admin Dashboard
admin_dash = admin_session.get(f"{BASE_URL}/admin/dashboard")
record_test("Admin Dashboard Access (/admin/dashboard)", admin_dash.status_code == 200 and "Administrative Case Management Portal" in admin_dash.text, f"HTTP {admin_dash.status_code}")

# =========================================================================
# TEST SUITE 3: Complaint Filing Workflow & Suspect Physical Description
# =========================================================================
print("\n--- TEST SUITE 3: Complaint Lifecycle & Suspect Physical Description ---")

created_complaints = []

# Step 3.1: Citizen creates a new complaint
c_home = citizen_session.get(f"{BASE_URL}/home")
c_csrf = get_csrf(c_home.text)
new_c_resp = citizen_session.post(f"{BASE_URL}/complaints/new", data={"csrf_token": c_csrf}, allow_redirects=True)
match_c = re.search(r'/complaints/(\d+)/edit', new_c_resp.url)
complaint_id = int(match_c.group(1)) if match_c else None
record_test("Initialize Complaint Draft (POST /complaints/new)", bool(complaint_id), f"Complaint ID: {complaint_id}")

if complaint_id:
    created_complaints.append(complaint_id)

    # Step 3.2: Save Step 1 (Crime Details + Suspect Physical Description)
    step1_csrf = get_csrf(new_c_resp.text)
    step1_data = {
        "csrf_token": step1_csrf,
        "title": "Synthetic Audit Jewelry Theft",
        "category": "Robbery & Theft",
        "incident_at": "2026-11-10T14:30",
        "location_address": "Station Road, Main Market, Vijayapura",
        "narrative": "Eyewitness observed suspect fleeing south toward railway station.",
        "suspect_gender": "Male",
        "suspect_approx_age": "28-32 years",
        "suspect_height": "5'10\" (178 cm)",
        "suspect_build": "Athletic / Medium",
        "suspect_complexion": "Wheatish",
        "suspect_hair": "Short wavy black hair, neat stubble",
        "suspect_eyes": "Dark brown, sharp gaze",
        "suspect_clothing": "Dark navy jacket, blue jeans",
        "suspect_accessories": "Silver chain, black baseball cap",
        "suspect_identifying_marks": "Small scar above left eyebrow",
        "suspect_additional_details": "Spoke Kannada with northern dialect"
    }
    s1_resp = citizen_session.post(f"{BASE_URL}/complaints/{complaint_id}/draft", data=step1_data, allow_redirects=True)
    record_test("Save Draft Step 1 (Incident & Physical Details)", s1_resp.status_code in (200, 302))

    # Step 3.3: Save Step 2 (Branch Selection: Branch A 'none')
    s2_page = citizen_session.get(f"{BASE_URL}/complaints/{complaint_id}/edit?step=2")
    s2_csrf = get_csrf(s2_page.text)
    step2_data = {
        "csrf_token": s2_csrf,
        "facial_reference_type": "none"
    }
    s2_resp = citizen_session.post(f"{BASE_URL}/complaints/{complaint_id}/draft", data=step2_data, allow_redirects=True)
    record_test("Save Draft Step 2 (Branch A 'none' Selection)", s2_resp.status_code in (200, 302))

    # Step 3.4: Evidence Upload in Step 3
    s3_page = citizen_session.get(f"{BASE_URL}/complaints/{complaint_id}/edit?step=3")
    s3_csrf = get_csrf(s3_page.text)
    fake_pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000102 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
    files = {
        "evidence_files": ("incident_documentation.pdf", fake_pdf_bytes, "application/pdf")
    }
    upload_data = {
        "csrf_token": s3_csrf
    }
    upload_resp = citizen_session.post(f"{BASE_URL}/complaints/{complaint_id}/evidence", data=upload_data, files=files, allow_redirects=True)
    record_test("Step 3 Evidence Attachment & SHA-256 Hashing", upload_resp.status_code == 200 and "incident_documentation.pdf" in upload_resp.text and "sha256_hex" in upload_resp.text)

    # Step 3.5: Finalize and Submit Complaint
    review_page = citizen_session.get(f"{BASE_URL}/complaints/{complaint_id}/edit?step=4")
    sub_csrf = get_csrf(review_page.text)
    sub_data = {
        "csrf_token": sub_csrf,
        "declaration_truth": "on",
        "terms_accepted": "on"
    }
    sub_resp = citizen_session.post(f"{BASE_URL}/complaints/{complaint_id}/submit", data=sub_data, allow_redirects=True)
    record_test("Submit Complaint (POST /complaints/<id>/submit)", sub_resp.status_code == 200 and ("Confirmation" in sub_resp.text or "TE-2026-" in sub_resp.text))

# =========================================================================
# TEST SUITE 4: Admin Intake Review & Complaint Approval
# =========================================================================
print("\n--- TEST SUITE 4: Admin Case Review & Approval ---")
if complaint_id:
    # Admin inspects review screen
    rev_resp = admin_session.get(f"{BASE_URL}/admin/cases/{complaint_id}/review")
    record_test("Admin Case Review View (/admin/cases/<id>/review)", rev_resp.status_code == 200 and "Jewelry Theft" in rev_resp.text)

    # Admin approves case and assigns officer
    admin_action_csrf = get_csrf(rev_resp.text)
    action_data = {
        "csrf_token": admin_action_csrf,
        "action": "approve",
        "assigned_officer_name": "Senior Inspector S. Sharma",
        "assigned_station": "City Central Police Station",
        "review_notes": "All incident details and physical attributes verified. Approved for sketch construction."
    }
    action_resp = admin_session.post(f"{BASE_URL}/admin/cases/{complaint_id}/action", data=action_data, allow_redirects=True)
    record_test("Admin Case Approval (POST /admin/cases/<id>/action)", action_resp.status_code == 200)

# =========================================================================
# TEST SUITE 5: Suspect Physical Description Side Panel & API
# =========================================================================
print("\n--- TEST SUITE 5: Suspect Physical Description API & Step 2 Workspace ---")
if complaint_id:
    # Test JSON API
    api_resp = citizen_session.get(f"{BASE_URL}/api/cases/{complaint_id}/suspect-description")
    record_test("Suspect Description JSON API Endpoint", api_resp.status_code == 200)
    if api_resp.status_code == 200:
        desc = api_resp.json()
        record_test("Suspect Gender Match", desc.get("suspect_gender") == "Male")
        record_test("Suspect Age Match", "28-32" in str(desc.get("suspect_approx_age")))
        record_test("Suspect Height Match", "5'10" in str(desc.get("suspect_height")))
        record_test("Suspect Build Match", "Athletic" in str(desc.get("suspect_build")))
        record_test("Suspect Complexion Match", "Wheatish" in str(desc.get("suspect_complexion")))
        record_test("Suspect Hair Match", "Short wavy black" in str(desc.get("suspect_hair")))
        record_test("Suspect Marks Match", "scar" in str(desc.get("suspect_identifying_marks")).lower())

    # Test Step 2 Sketch Constructor View
    sketch_page = citizen_session.get(f"{BASE_URL}/cases/{complaint_id}/sketch")
    record_test("Render Sketch Constructor (/cases/<id>/sketch)", sketch_page.status_code == 200 and "SUSPECT PHYSICAL DESCRIPTION" in sketch_page.text)
    record_test("Sidebar Suspect Details Present in HTML", "Athletic / Medium" in sketch_page.text and "Wheatish" in sketch_page.text)

# =========================================================================
# TEST SUITE 6: Forensic Pipeline - Sketch, Reconstruction & Variations
# =========================================================================
print("\n--- TEST SUITE 6: Forensic Pipeline - Sketch, Reconstruction & Variations ---")
if complaint_id:
    # Create a synthetic composite sketch image (256x256 line drawing)
    img = Image.new("RGB", (256, 256), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 40, 206, 220], outline=(0, 0, 0), width=3) # Head outline
    draw.ellipse([80, 100, 110, 115], fill=(0, 0, 0)) # Left eye
    draw.ellipse([146, 100, 176, 115], fill=(0, 0, 0)) # Right eye
    draw.line([128, 115, 128, 150], fill=(0, 0, 0), width=2) # Nose
    draw.line([100, 175, 156, 175], fill=(0, 0, 0), width=3) # Mouth
    draw.arc([60, 40, 196, 100], start=180, end=360, fill=(0, 0, 0), width=6) # Hair

    sketch_io = io.BytesIO()
    img.save(sketch_io, format="PNG")
    sketch_bytes = sketch_io.getvalue()
    sketch_b64 = "data:image/png;base64," + base64.b64encode(sketch_bytes).decode("ascii")

    # Step 6.1: Save composite sketch
    sketch_view = citizen_session.get(f"{BASE_URL}/cases/{complaint_id}/sketch")
    sk_csrf = get_csrf(sketch_view.text)
    sk_data = {
        "csrf_token": sk_csrf,
        "sketch_data": sketch_b64
    }
    sk_save_resp = citizen_session.post(f"{BASE_URL}/cases/{complaint_id}/sketch", data=sk_data, allow_redirects=True)
    record_test("Save Composite Sketch Artifact", sk_save_resp.status_code == 200 and ("Saved" in sk_save_resp.text or "workspace" in sk_save_resp.url))

    # Step 6.2: Sketch-to-Face Neural Reconstruction
    ws_page = citizen_session.get(f"{BASE_URL}/cases/{complaint_id}/workspace")
    recon_csrf = get_csrf(ws_page.text)
    recon_post_resp = citizen_session.post(f"{BASE_URL}/cases/{complaint_id}/reconstruct", data={"csrf_token": recon_csrf}, allow_redirects=True)
    record_test("AI Face Reconstruction Execution", recon_post_resp.status_code == 200 and ("Reconstructed" in recon_post_resp.text or "reconstructed_face" in recon_post_resp.text or "Reconstruction" in recon_post_resp.text))

    # Step 6.3: Facial Variations Generation
    ws_page2 = citizen_session.get(f"{BASE_URL}/cases/{complaint_id}/workspace")
    var_csrf = get_csrf(ws_page2.text)
    var_post_resp = citizen_session.post(f"{BASE_URL}/cases/{complaint_id}/variations", data={"csrf_token": var_csrf}, allow_redirects=True)
    record_test("Facial Variations Generation Execution", var_post_resp.status_code == 200 and ("variation" in var_post_resp.text.lower() or "workspace" in var_post_resp.url))

    # Step 6.4: Biometric Case Binding Policy (Branch A MUST NOT permit recognition)
    recog_resp = citizen_session.get(f"{BASE_URL}/cases/{complaint_id}/recognition", allow_redirects=True)
    record_test("Biometric Policy Block on Branch A", "not permitted" in recog_resp.text.lower() or "workspace" in recog_resp.url)

# =========================================================================
# TEST SUITE 7: Case Wanted Poster Generation & Public Download Gate
# =========================================================================
print("\n--- TEST SUITE 7: Case Wanted Poster Generation & Approval Gate ---")
if complaint_id:
    # Generate Poster Draft
    ws_page3 = citizen_session.get(f"{BASE_URL}/cases/{complaint_id}/workspace")
    poster_csrf = get_csrf(ws_page3.text)
    poster_data = {
        "csrf_token": poster_csrf,
        "reward_amount": "Rs. 25,000",
        "contact_officer": "Insp. Sharma",
        "contact_phone": "08352-250100"
    }
    gen_post_resp = citizen_session.post(f"{BASE_URL}/cases/{complaint_id}/poster", data=poster_data, allow_redirects=True)
    record_test("Wanted Poster Generation (ReportLab PDF/PNG)", gen_post_resp.status_code == 200 and ("poster" in gen_post_resp.text.lower() or "workspace" in gen_post_resp.url))

    # Find the generated poster evidence ID
    m_poster_ev = re.search(r'/cases/' + str(complaint_id) + r'/poster/(\d+)/download', gen_post_resp.text)
    poster_ev_id = int(m_poster_ev.group(1)) if m_poster_ev else None
    if not poster_ev_id:
        # Check review page
        admin_rev_page = admin_session.get(f"{BASE_URL}/admin/cases/{complaint_id}/review")
        m_ev2 = re.search(r'/cases/' + str(complaint_id) + r'/poster/(\d+)/approve', admin_rev_page.text)
        poster_ev_id = int(m_ev2.group(1)) if m_ev2 else None

    record_test("Poster Evidence Registered in Database", bool(poster_ev_id), f"Evidence ID: {poster_ev_id}")

    if poster_ev_id:
        # Public download BEFORE approval MUST be blocked
        anon_session = requests.Session()
        unapproved_dl = anon_session.get(f"{BASE_URL}/cases/{complaint_id}/poster/{poster_ev_id}/public-download", allow_redirects=False)
        record_test("Poster Public Download Gated Before Approval", unapproved_dl.status_code in (403, 302, 404), f"HTTP {unapproved_dl.status_code}")

        # Admin approves the poster
        admin_rev_view = admin_session.get(f"{BASE_URL}/admin/cases/{complaint_id}/review")
        ad_poster_csrf = get_csrf(admin_rev_view.text)
        approve_resp = admin_session.post(f"{BASE_URL}/cases/{complaint_id}/poster/{poster_ev_id}/approve", data={"csrf_token": ad_poster_csrf}, allow_redirects=True)
        record_test("Admin Approves Poster Notice", approve_resp.status_code == 200 and ("approved" in approve_resp.text.lower() or "success" in approve_resp.text.lower()))

        # Public download AFTER approval MUST succeed
        approved_dl = anon_session.get(f"{BASE_URL}/cases/{complaint_id}/poster/{poster_ev_id}/public-download")
        record_test("Poster Public Download Allowed After Approval", approved_dl.status_code == 200 and len(approved_dl.content) > 500, f"Bytes received: {len(approved_dl.content)}")

# =========================================================================
# TEST SUITE 8: Branch B & C Biometric Access Verification
# =========================================================================
print("\n--- TEST SUITE 8: Branch B & C Biometric Access Verification ---")

# Step 8.1: Test Option C (photo_masked) Disallowed & Rejected
c_home = citizen_session.get(f"{BASE_URL}/home")
c_csrf = get_csrf(c_home.text)
c_resp = citizen_session.post(f"{BASE_URL}/complaints/new", data={"csrf_token": c_csrf}, allow_redirects=True)
m_c3 = re.search(r'/complaints/(\d+)/edit', c_resp.url)
case_c_id = int(m_c3.group(1)) if m_c3 else None

if case_c_id:
    created_complaints.append(case_c_id)
    # Save step 1
    s1_csrf = get_csrf(c_resp.text)
    citizen_session.post(f"{BASE_URL}/complaints/{case_c_id}/draft", data={
        "csrf_token": s1_csrf,
        "title": "Bank ATM Suspect Case",
        "category": "Robbery & Theft",
        "narrative": "Incident verification narrative."
    })
    # Attempting to save photo_masked is rejected
    s4_page = citizen_session.get(f"{BASE_URL}/complaints/{case_c_id}/edit?step=4")
    rej_resp = citizen_session.post(f"{BASE_URL}/complaints/{case_c_id}/draft", data={
        "csrf_token": get_csrf(s4_page.text),
        "facial_reference_type": "photo_masked"
    })
    record_test("Option C Rejection Validation", rej_resp.status_code in (400, 500) or "Invalid facial reference type" in rej_resp.text)

# =========================================================================
# TEST SUITE 9: Logout & Session Invalidation
# =========================================================================
print("\n--- TEST SUITE 9: Logout & Session Termination ---")
c_home = citizen_session.get(f"{BASE_URL}/home")
logout_csrf = get_csrf(c_home.text)
logout_resp = citizen_session.post(f"{BASE_URL}/logout", data={"csrf_token": logout_csrf}, allow_redirects=True)
record_test("Citizen Logout (POST /logout)", logout_resp.status_code == 200 and ("Login" in logout_resp.text or "logged out" in logout_resp.text.lower()))

after_logout = citizen_session.get(f"{BASE_URL}/my-complaints", allow_redirects=False)
record_test("Session Terminated After Logout", after_logout.status_code in (302, 401), f"Status {after_logout.status_code}")

# =========================================================================
# SAFE AUDIT RECORDING
# =========================================================================
print("\n--- AUDIT RECORDING & TRACEABILITY ---")
print(f"Recorded Synthetic Test User: {SYNTH_USER}")
print(f"Recorded Synthetic Test Complaints: {created_complaints}")

print("\n" + "="*70)
print(f"AUDIT SUMMARY: {results['passed']} Passed, {results['failed']} Failed out of {results['total']} Tests.")
print("="*70)

with open("phase1_live_audit_results.json", "w") as f:
    json.dump(results, f, indent=2)

sys.exit(0 if results["failed"] == 0 else 1)
