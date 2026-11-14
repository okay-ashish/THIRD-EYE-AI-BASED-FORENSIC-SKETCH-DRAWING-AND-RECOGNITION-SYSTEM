-- =========================================================
-- ThirdEye — Database Schema & Sample Setup
-- =========================================================
-- Database: thirdeye_db
-- Compatibility: MySQL 5.7+ / MySQL 8.0+ / MariaDB 10.3+
-- =========================================================

CREATE DATABASE IF NOT EXISTS `thirdeye_db` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `thirdeye_db`;

-- ---------------------------------------------------------
-- Table structure for table `users`
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(100) DEFAULT NULL,
  `username` varchar(80) NOT NULL,
  `password` varchar(200) NOT NULL,
  `role` varchar(20) NOT NULL DEFAULT 'user',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username_UNIQUE` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Table structure for table `persons`
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS `persons` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `person_details` text,
  `image_path` varchar(200) NOT NULL,
  `face_encoding` longtext NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Table structure for table `complaints`
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS `complaints` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `complaint_number` varchar(50) NOT NULL,
  `created_by_id` int(11) NOT NULL,
  `reporter_relationship` varchar(50) DEFAULT NULL,
  `complainant_context` text DEFAULT NULL,
  `title` varchar(200) DEFAULT NULL,
  `category` varchar(100) DEFAULT NULL,
  `narrative` text DEFAULT NULL,
  `transcription_raw` text DEFAULT NULL,
  `incident_at` datetime DEFAULT NULL,
  `location_address` varchar(500) DEFAULT NULL,
  `latitude` double DEFAULT NULL,
  `longitude` double DEFAULT NULL,
  `location_source` varchar(50) DEFAULT NULL,
  `location_notes` text DEFAULT NULL,
  `suspect_approx_age` varchar(50) DEFAULT NULL,
  `suspect_gender` varchar(30) DEFAULT NULL,
  `suspect_height` varchar(50) DEFAULT NULL,
  `suspect_build` varchar(50) DEFAULT NULL,
  `suspect_complexion` varchar(50) DEFAULT NULL,
  `suspect_hair` varchar(100) DEFAULT NULL,
  `suspect_eyes` varchar(100) DEFAULT NULL,
  `suspect_clothing` text DEFAULT NULL,
  `suspect_accessories` text DEFAULT NULL,
  `suspect_mask_description` text DEFAULT NULL,
  `suspect_identifying_marks` text DEFAULT NULL,
  `suspect_additional_details` text DEFAULT NULL,
  `facial_reference_type` varchar(50) NOT NULL DEFAULT 'none',
  `status` varchar(40) NOT NULL DEFAULT 'draft',
  `assigned_officer_name` varchar(100) DEFAULT NULL,
  `assigned_officer_id` varchar(50) DEFAULT NULL,
  `assigned_station` varchar(100) DEFAULT NULL,
  `assigned_officer_contact` varchar(100) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `closed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `complaint_number_UNIQUE` (`complaint_number`),
  KEY `idx_complaints_created_by` (`created_by_id`),
  KEY `idx_complaints_status_created` (`status`, `created_at`),
  CONSTRAINT `fk_complaints_created_by` FOREIGN KEY (`created_by_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Table structure for table `complaint_evidence`
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS `complaint_evidence` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `complaint_id` int(11) NOT NULL,
  `uploaded_by_id` int(11) DEFAULT NULL,
  `source_evidence_id` int(11) DEFAULT NULL,
  `evidence_type` varchar(50) NOT NULL DEFAULT 'photo',
  `source_kind` varchar(20) NOT NULL DEFAULT 'uploaded',
  `storage_path` varchar(500) NOT NULL,
  `original_filename` varchar(255) DEFAULT NULL,
  `mime_type` varchar(100) DEFAULT NULL,
  `file_size_bytes` bigint(20) DEFAULT NULL,
  `sha256_hex` varchar(64) DEFAULT NULL,
  `generation_method` varchar(200) DEFAULT NULL,
  `access_level` varchar(50) NOT NULL DEFAULT 'restricted',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `storage_path_UNIQUE` (`storage_path`),
  KEY `idx_evidence_complaint_id` (`complaint_id`),
  KEY `idx_evidence_uploaded_by` (`uploaded_by_id`),
  KEY `idx_evidence_source_id` (`source_evidence_id`),
  CONSTRAINT `fk_evidence_complaint` FOREIGN KEY (`complaint_id`) REFERENCES `complaints` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_evidence_uploader` FOREIGN KEY (`uploaded_by_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_evidence_source` FOREIGN KEY (`source_evidence_id`) REFERENCES `complaint_evidence` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Table structure for table `complaint_timeline`
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS `complaint_timeline` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `complaint_id` int(11) NOT NULL,
  `actor_user_id` int(11) DEFAULT NULL,
  `event_type` varchar(100) NOT NULL,
  `previous_status` varchar(50) DEFAULT NULL,
  `new_status` varchar(50) DEFAULT NULL,
  `message` text DEFAULT NULL,
  `is_visible_to_user` tinyint(1) NOT NULL DEFAULT 0,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_timeline_complaint_created` (`complaint_id`, `created_at`),
  KEY `idx_timeline_actor_id` (`actor_user_id`),
  CONSTRAINT `fk_timeline_complaint` FOREIGN KEY (`complaint_id`) REFERENCES `complaints` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_timeline_actor` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Sample Seed Data for Local Development
-- (Note: Create admin securely using `python create_admin.py`)
-- ---------------------------------------------------------

-- Sample test person record with synthetic zero vector placeholder
-- (Replace or add records through the ThirdEye Admin interface)
INSERT INTO `persons` (`id`, `name`, `person_details`, `image_path`, `face_encoding`) VALUES
(1, 'Demo Subject', 'Synthetic reference record for system verification', 'test_person.jpg', '0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0');
