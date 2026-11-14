#!/usr/bin/env python3
"""
ThirdEye Isolated Test Suite — Suspect Description Side Panel in Face Construction
===================================================================================
Verifies:
Test 1: Correct Description Display in Step 2 side panel
Test 2: Multiple Cases data isolation (no leakage between cases)
Test 3: Access Control (cross-user 403 Forbidden, unauthenticated login redirect)
Test 4: Empty / omitted optional fields handled gracefully with 'Not provided'
Test 5: Long descriptions rendered completely without breaking layouts
Test 6: Existing composite sketch construction and saving preserved
Test 7: Read-only GET access does not modify or overwrite Step 1 data
"""

import os
import io
import sys
import html as html_lib
import unittest
import tempfile
import shutil
import base64
from unittest.mock import patch
from datetime import datetime

# Enforce SQLite in-memory before app import
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['FLASK_ENV'] = 'testing'
os.environ['TESTING'] = 'True'
os.environ['THIRDEYE_SECRET_KEY'] = 'isolated_test_secret_key_suspect_panel_123'
os.environ['THIRDEYE_DB_NAME'] = 'isolated_test_memory'

import app as app_module
from app import app, db
from models import User, Complaint, ComplaintEvidence, ComplaintTimeline
from services.complaint_service import (
    create_draft_complaint,
    update_draft_complaint,
    submit_complaint
)
from services.workflow_service import (
    get_case_for_user,
    transition_case_status,
    can_access_tool,
    save_case_artifact
)


class SuspectDescriptionPanelTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app_module._last_cleanup_timestamp = 9999999999.0

        cls.test_storage_root = tempfile.mkdtemp(prefix="thirdeye_panel_test_storage_")
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
        self.admin_user = User(username='inspector_gadget', password='AdminPassword123!', role='admin', full_name='Inspector Gadget')
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

    def test_01_correct_description_display(self):
        """Test 1 — Correct Description Display: Step 1 data is displayed in Step 2 side panel."""
        self._login(self.user_a)
        complaint = create_draft_complaint(self.user_a.id)

        unique_desc = {
            'title': 'Nighttime Jewel Heist',
            'category': 'Burglary',
            'narrative': 'Masked subject entered via second-floor window.',
            'facial_reference_type': 'none',
            'suspect_gender': 'Male',
            'suspect_approx_age': '28-32 years',
            'suspect_height': "5'11\"",
            'suspect_build': 'Athletic / Lean',
            'suspect_complexion': 'Wheatish / Medium Tan',
            'suspect_hair': 'Short curly dark hair, trimmed sideburns',
            'suspect_eyes': 'Dark brown piercing eyes with wireframe spectacles',
            'suspect_clothing': 'Navy hooded sweatshirt, dark tactical pants',
            'suspect_accessories': 'Black canvas backpack with orange trim',
            'suspect_mask_description': 'Black cloth half-mask pulled below chin',
            'suspect_identifying_marks': 'Prominent 3-inch scar on left forearm',
            'suspect_additional_details': 'Spoke with hurried northern dialect, brisk athletic gait.'
        }
        update_draft_complaint(complaint.id, self.user_a.id, unique_desc)

        # Open Step 2 (Face Construction)
        resp = self.client.get(f'/cases/{complaint.id}/sketch')
        self.assertEqual(resp.status_code, 200)

        html = html_lib.unescape(resp.data.decode('utf-8'))

        # Verify side panel header and structure in LEFT sidebar
        self.assertIn('SUSPECT PHYSICAL DESCRIPTION', html)
        self.assertIn('Saved from Step 1 (Complaint)', html)
        self.assertIn("Use the suspect's physical description as a reference", html)
        self.assertIn('sidebarSuspectContainer', html)

        # Verify RIGHT side panel is completely removed
        self.assertNotIn('suspectDescriptionPanel', html)
        self.assertNotIn('class="suspect-description-panel"', html)

        # Verify navigation menu is replaced in sidebar on this page
        self.assertNotIn('<span>File Complaint</span>', html)
        self.assertNotIn('<span>My Complaints</span>', html)

        # Verify brand header and user profile remain present
        self.assertIn('THIRDEYE', html)
        self.assertIn('Alice Citizen', html)

        # Verify all unique descriptor values from Step 1 appear in the response
        self.assertIn('28-32 years', html)
        self.assertIn("5'11\"", html)
        self.assertIn('Athletic / Lean', html)
        self.assertIn('Wheatish / Medium Tan', html)
        self.assertIn('Short curly dark hair, trimmed sideburns', html)
        self.assertIn('Dark brown piercing eyes with wireframe spectacles', html)
        self.assertIn('Navy hooded sweatshirt, dark tactical pants', html)
        self.assertIn('Black canvas backpack with orange trim', html)
        self.assertIn('Black cloth half-mask pulled below chin', html)
        self.assertIn('Prominent 3-inch scar on left forearm', html)
        self.assertIn('Spoke with hurried northern dialect, brisk athletic gait.', html)

    def test_02_multiple_cases_isolation(self):
        """Test 2 — Multiple Cases: Each case displays only its own saved suspect description."""
        self._login(self.user_a)

        # Case 1: Alpha
        case_1 = create_draft_complaint(self.user_a.id)
        update_draft_complaint(case_1.id, self.user_a.id, {
            'title': 'Case Alpha - Downtown Bank',
            'category': 'Robbery',
            'narrative': 'Incident Alpha',
            'facial_reference_type': 'none',
            'suspect_approx_age': '45-50 years',
            'suspect_height': "6'3\"",
            'suspect_build': 'Heavyweight / Stocky',
            'suspect_clothing': 'Bright yellow safety vest'
        })

        # Case 2: Beta
        case_2 = create_draft_complaint(self.user_a.id)
        update_draft_complaint(case_2.id, self.user_a.id, {
            'title': 'Case Beta - Suburb Pharmacy',
            'category': 'Shoplifting',
            'narrative': 'Incident Beta',
            'facial_reference_type': 'none',
            'suspect_approx_age': '19-22 years',
            'suspect_height': "5'4\"",
            'suspect_build': 'Slim / Petite',
            'suspect_clothing': 'Red zip-up jacket'
        })

        # Check Case 1
        resp_1 = self.client.get(f'/cases/{case_1.id}/sketch')
        self.assertEqual(resp_1.status_code, 200)
        html_1 = html_lib.unescape(resp_1.data.decode('utf-8'))
        self.assertIn('Case Alpha - Downtown Bank', html_1)
        self.assertIn('45-50 years', html_1)
        self.assertIn("6'3\"", html_1)
        self.assertIn('Bright yellow safety vest', html_1)
        # Case 2 data must NOT appear in Case 1
        self.assertNotIn('Case Beta - Suburb Pharmacy', html_1)
        self.assertNotIn('19-22 years', html_1)
        self.assertNotIn("5'4\"", html_1)
        self.assertNotIn('Red zip-up jacket', html_1)

        # Check Case 2
        resp_2 = self.client.get(f'/cases/{case_2.id}/sketch')
        self.assertEqual(resp_2.status_code, 200)
        html_2 = html_lib.unescape(resp_2.data.decode('utf-8'))
        self.assertIn('Case Beta - Suburb Pharmacy', html_2)
        self.assertIn('19-22 years', html_2)
        self.assertIn("5'4\"", html_2)
        self.assertIn('Red zip-up jacket', html_2)
        # Case 1 data must NOT appear in Case 2
        self.assertNotIn('Case Alpha - Downtown Bank', html_2)
        self.assertNotIn('45-50 years', html_2)
        self.assertNotIn("6'3\"", html_2)
        self.assertNotIn('Bright yellow safety vest', html_2)

    def test_03_access_control(self):
        """Test 3 — Access Control: Citizen B cannot view Citizen A's case suspect description."""
        # Create case for User A
        self._login(self.user_a)
        case_a = create_draft_complaint(self.user_a.id)
        update_draft_complaint(case_a.id, self.user_a.id, {
            'title': 'Confidential Investigation A',
            'category': 'Extortion',
            'narrative': 'Classified citizen details',
            'facial_reference_type': 'none',
            'suspect_additional_details': 'CONFIDENTIAL_SECRET_MARKER_9988'
        })

        # 1. Unauthenticated attempt -> redirect to login (302)
        with self.client.session_transaction() as sess:
            sess.clear()
        resp_unauth = self.client.get(f'/cases/{case_a.id}/sketch')
        self.assertEqual(resp_unauth.status_code, 302)
        self.assertIn('/login', resp_unauth.headers['Location'])

        # 2. Authenticated as User B -> 403 Forbidden
        self._login(self.user_b)
        resp_forbidden = self.client.get(f'/cases/{case_a.id}/sketch')
        self.assertEqual(resp_forbidden.status_code, 403)

        # 3. Authenticated as Admin -> 200 OK (admin can view case)
        self._login(self.admin_user)
        resp_admin = self.client.get(f'/cases/{case_a.id}/sketch')
        self.assertEqual(resp_admin.status_code, 200)
        self.assertIn('CONFIDENTIAL_SECRET_MARKER_9988', resp_admin.data.decode('utf-8'))

    def test_04_empty_description_handling(self):
        """Test 4 — Empty Description: Missing optional fields display 'Not provided' gracefully without errors."""
        self._login(self.user_a)
        complaint = create_draft_complaint(self.user_a.id)
        update_draft_complaint(complaint.id, self.user_a.id, {
            'title': 'Minimal Report',
            'category': 'Vandalism',
            'narrative': 'Graffiti on storefront wall',
            'facial_reference_type': 'none'
            # All suspect fields left blank / null
        })

        resp = self.client.get(f'/cases/{complaint.id}/sketch')
        self.assertEqual(resp.status_code, 200)

        html = resp.data.decode('utf-8')
        self.assertIn('SUSPECT PHYSICAL DESCRIPTION', html)
        self.assertIn('Not provided', html)
        # Ensure workspace elements rendered without syntax crash
        self.assertIn('id="sketchCanvas"', html)
        self.assertIn('id="sketch-workspace"', html)

    def test_05_long_description_rendering_and_scrolling(self):
        """Test 5 — Long Description: Lengthy text is fully rendered and side panel has scrollable container."""
        self._login(self.user_a)
        complaint = create_draft_complaint(self.user_a.id)

        long_marks = "TATTOO_PARAGRAPH: " + ("Dragon motif wrapping around shoulder to forearm. " * 20)
        long_additional = "ADDITIONAL_OBSERVATIONS: " + ("Witness observed distinct limping gait on right foot with rapid pace. " * 25)

        update_draft_complaint(complaint.id, self.user_a.id, {
            'title': 'Lengthy Observation Case',
            'category': 'Robbery',
            'narrative': 'Lengthy narrative test.',
            'facial_reference_type': 'none',
            'suspect_identifying_marks': long_marks,
            'suspect_additional_details': long_additional
        })

        resp = self.client.get(f'/cases/{complaint.id}/sketch')
        self.assertEqual(resp.status_code, 200)

        html = resp.data.decode('utf-8')
        self.assertIn('TATTOO_PARAGRAPH:', html)
        self.assertIn('ADDITIONAL_OBSERVATIONS:', html)
        # Verify scrollable CSS class is applied to container
        self.assertIn('suspect-panel-content', html)
        self.assertIn('overflow-y: auto;', html)

    def test_06_existing_sketch_functionality_preserved(self):
        """Test 6 — Existing Sketch Functionality: Canvas, controls, and artifact saving remain operational."""
        self._login(self.user_a)
        complaint = create_draft_complaint(self.user_a.id)
        update_draft_complaint(complaint.id, self.user_a.id, {
            'title': 'Workflow Preservation Test',
            'category': 'Robbery',
            'narrative': 'Preservation test',
            'facial_reference_type': 'none',
            'suspect_gender': 'Female',
            'suspect_approx_age': '24'
        })

        # 1. GET verifies canvas and category tabs exist
        resp_get = self.client.get(f'/cases/{complaint.id}/sketch')
        self.assertEqual(resp_get.status_code, 200)
        html_get = resp_get.data.decode('utf-8')
        for cat in ['head', 'hair', 'eyebrows', 'eyes', 'nose', 'lips', 'mustach', 'more']:
            self.assertIn(f'data-category="{cat}"', html_get)
        self.assertIn('id="constructFaceBtn"', html_get)

        # 2. POST saves sketch image
        dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        data_url = 'data:image/png;base64,' + base64.b64encode(dummy_png).decode('ascii')

        resp_post = self.client.post(
            f'/cases/{complaint.id}/sketch',
            data={'sketch_data': data_url, 'skin_tone': 'medium'},
            follow_redirects=False
        )
        # Should redirect back to draft wizard step 4
        self.assertEqual(resp_post.status_code, 302)
        self.assertIn(f'/complaints/{complaint.id}/edit', resp_post.headers['Location'])

        # 3. Verify ComplaintEvidence registered
        ev = ComplaintEvidence.query.filter_by(complaint_id=complaint.id, evidence_type='sketch').first()
        self.assertIsNotNone(ev, "Sketch artifact was not registered in ComplaintEvidence")
        self.assertEqual(ev.source_kind, 'generated')
        self.assertEqual(ev.generation_method, 'composite_layers')

    def test_07_no_data_modification_on_step2_get(self):
        """Test 7 — No Data Modification: Opening Step 2 never mutates or overwrites Step 1 data."""
        self._login(self.user_a)
        complaint = create_draft_complaint(self.user_a.id)

        initial_data = {
            'title': 'Immutability Verification Case',
            'category': 'Assault',
            'narrative': 'Original pristine witness narrative.',
            'facial_reference_type': 'none',
            'suspect_gender': 'Male',
            'suspect_approx_age': '35',
            'suspect_height': "6'0\"",
            'suspect_build': 'Muscular',
            'suspect_complexion': 'Fair',
            'suspect_hair': 'Brown crew cut',
            'suspect_eyes': 'Blue eyes',
            'suspect_clothing': 'Grey track jacket',
            'suspect_accessories': 'Silver necklace',
            'suspect_mask_description': 'None',
            'suspect_identifying_marks': 'Dragon tattoo on neck',
            'suspect_additional_details': 'Deep bass voice'
        }
        update_draft_complaint(complaint.id, self.user_a.id, initial_data)

        # Snapshot before GET
        db.session.refresh(complaint)
        updated_at_before = complaint.updated_at
        title_before = complaint.title
        narrative_before = complaint.narrative
        age_before = complaint.suspect_approx_age
        marks_before = complaint.suspect_identifying_marks
        clothing_before = complaint.suspect_clothing

        # Execute GET on Step 2
        resp = self.client.get(f'/cases/{complaint.id}/sketch')
        self.assertEqual(resp.status_code, 200)

        # Reload from database and verify zero mutation
        db.session.expire_all()
        reloaded = Complaint.query.get(complaint.id)
        self.assertEqual(reloaded.updated_at, updated_at_before, "Complaint updated_at was modified by GET request!")
        self.assertEqual(reloaded.title, title_before)
        self.assertEqual(reloaded.narrative, narrative_before)
        self.assertEqual(reloaded.suspect_approx_age, age_before)
        self.assertEqual(reloaded.suspect_identifying_marks, marks_before)
        self.assertEqual(reloaded.suspect_clothing, clothing_before)

    def test_08_api_suspect_description_endpoint(self):
        """Test 8 — Backend API: GET /api/cases/<id>/suspect-description delivers exact JSON and enforces RBAC."""
        self._login(self.user_a)
        complaint = create_draft_complaint(self.user_a.id)
        update_draft_complaint(complaint.id, self.user_a.id, {
            'title': 'API Suspect Profile Test',
            'category': 'Fraud',
            'narrative': 'Test description API delivery',
            'facial_reference_type': 'none',
            'suspect_gender': 'Male',
            'suspect_approx_age': '30-35',
            'suspect_height': "5'10\"",
            'suspect_build': 'Medium',
            'suspect_complexion': 'Fair',
            'suspect_hair': 'Black short with goatee beard',
            'suspect_eyes': 'Hazel',
            'suspect_mask_description': 'Blue medical mask',
            'suspect_identifying_marks': 'Mole on right cheek',
            'suspect_clothing': 'Grey suit jacket',
            'suspect_accessories': 'Leather briefcase',
            'suspect_additional_details': 'Carried silver pen'
        })

        # 1. Successful JSON fetch by owner
        resp = self.client.get(f'/api/cases/{complaint.id}/suspect-description')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['suspect_gender'], 'Male')
        self.assertEqual(data['suspect_approx_age'], '30-35')
        self.assertEqual(data['suspect_height'], "5'10\"")
        self.assertEqual(data['suspect_build'], 'Medium')
        self.assertEqual(data['suspect_complexion'], 'Fair')
        self.assertEqual(data['suspect_hair'], 'Black short with goatee beard')
        self.assertEqual(data['suspect_facial_hair'], 'Black short with goatee beard')
        self.assertEqual(data['suspect_eyes'], 'Hazel')
        self.assertEqual(data['suspect_nose'], 'Not provided')
        self.assertEqual(data['suspect_lips'], 'Not provided')
        self.assertEqual(data['suspect_mask_description'], 'Blue medical mask')
        self.assertEqual(data['suspect_identifying_marks'], 'Mole on right cheek')
        self.assertEqual(data['suspect_clothing'], 'Grey suit jacket')
        self.assertEqual(data['suspect_accessories'], 'Leather briefcase')
        self.assertEqual(data['suspect_additional_details'], 'Carried silver pen')

        # 2. Cross-user access control (User B cannot query User A's API)
        self._login(self.user_b)
        resp_b = self.client.get(f'/api/cases/{complaint.id}/suspect-description')
        self.assertEqual(resp_b.status_code, 403)

        # 3. Admin access succeeds
        self._login(self.admin_user)
        resp_admin = self.client.get(f'/api/cases/{complaint.id}/suspect-description')
        self.assertEqual(resp_admin.status_code, 200)
        data_admin = resp_admin.get_json()
        self.assertTrue(data_admin['success'])
        self.assertEqual(data_admin['suspect_gender'], 'Male')


if __name__ == '__main__':
    unittest.main()
