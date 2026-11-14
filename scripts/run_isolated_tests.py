#!/usr/bin/env python3
"""
ThirdEye Isolated Test Runner — Phase 1
=========================================
Ensures 100% database and file-system isolation for automated tests.

Mandatory Constraints:
1. Enforces in-memory SQLite (sqlite:///:memory:) before application import.
2. Fails closed immediately if database backend is not SQLite.
3. Blocks raw MySQL connection attempts.
4. Prevents automatic background session garbage collection from touching dev files.
5. Confines all test database transactions to the isolated process memory.
"""

import os
import sys
import argparse
import unittest
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="[ISO-TEST] %(levelname)s: %(message)s")
logger = logging.getLogger("run_isolated_tests")

# On Windows with Anaconda, register Library\bin so sqlite3.dll and other C-extensions load cleanly
if sys.platform == "win32":
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

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def setup_isolation(fail_closed_test=False):
    """
    Configures environment variables and patches before any app imports
    to guarantee absolute database isolation.
    """
    if fail_closed_test:
        # Deliberately configure non-SQLite URI to verify fail-closed defense
        os.environ["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://fake_user:fake_pass@127.0.0.1:3306/fake_db"
    else:
        # Mandatory SQLite in-memory database
        os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    # Prevent .env loader from overriding test environment
    os.environ["FLASK_ENV"] = "testing"
    os.environ["TESTING"] = "True"
    os.environ["THIRDEYE_SECRET_KEY"] = "isolated_test_secret_key_1234567890abcdef"
    os.environ["THIRDEYE_DB_NAME"] = "isolated_test_memory"

    # Block raw MySQL connections at library level
    try:
        import mysql.connector
        def _blocked_mysql_connect(*args, **kwargs):
            raise RuntimeError("SECURITY VIOLATION: Direct MySQL connection blocked by isolated test runner!")
        mysql.connector.connect = _blocked_mysql_connect
    except ImportError:
        pass


def verify_isolated_app():
    """
    Imports the application and strictly verifies fail-closed SQLite backend.
    """
    import app as app_module
    from app import app, db
    from models import (
        User, Person, Complaint, ComplaintEvidence, ComplaintTimeline
    )

    # Enforce testing configuration
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["TEMP_RETENTION_HOURS"] = 999999

    # Suppress automatic background stale-session cleanup during tests
    # (prevents before_request from deleting existing development files)
    app_module._last_cleanup_timestamp = 9999999999.0

    # FAIL-CLOSED CHECK: Ensure SQLAlchemy dialect is strictly SQLite
    with app.app_context():
        dialect = db.engine.dialect.name
        if dialect != "sqlite":
            error_msg = (
                f"FATAL: Database isolation violation! Expected SQLite backend, found: '{dialect}'. "
                "Aborting immediately to protect live database!"
            )
            logger.critical(error_msg)
            sys.exit(101)

    return app, db, User, Person


def run_isolation_self_check():
    """
    Performs a lightweight verification of the isolated test environment:
    1. Validates SQLite backend
    2. Creates schema in memory
    3. Performs synthetic CRUD without touching live database
    4. Cleans up memory
    """
    logger.info("Starting Phase 1 lightweight test isolation self-check...")

    setup_isolation(fail_closed_test=False)
    app, db, User, Person = verify_isolated_app()

    with app.app_context():
        # 1. Create tables in memory
        db.create_all()
        logger.info("Isolated SQLite tables created successfully.")

        # Verify tables exist in SQLite metadata
        import sqlalchemy
        inspector = sqlalchemy.inspect(db.engine)
        tables = inspector.get_table_names()
        for expected in ("users", "persons", "complaints", "complaint_evidence", "complaint_timeline"):
            assert expected in tables, f"Table '{expected}' missing in isolated database"
        logger.info(f"Verified all 5 isolated tables: {tables}")

        # 2. Insert synthetic user
        test_username = "synth_iso_test_user"
        synthetic_user = User(
            username=test_username,
            password="SyntheticPassword123!",
            role="user",
            full_name="Synthetic User"
        )
        db.session.add(synthetic_user)
        db.session.commit()
        logger.info("Synthetic test user created in memory.")

        # 3. Query synthetic user
        queried = User.query.filter_by(username=test_username).first()
        assert queried is not None, "Failed to query synthetic user from memory"
        assert queried.full_name == "Synthetic User", "Synthetic user attribute mismatch"
        assert queried.check_password("SyntheticPassword123!"), "Password hash verification failed"
        assert not queried.check_password("WrongPassword"), "Password hash verification failed on negative test"
        logger.info("Synthetic user CRUD verification: PASSED.")

        # 4. Clean up synthetic user
        db.session.delete(queried)
        db.session.commit()
        assert User.query.filter_by(username=test_username).first() is None, "Synthetic user deletion failed"
        logger.info("Synthetic user cleanup: PASSED.")

        # 5. Drop tables to ensure clean slate
        db.drop_all()
        logger.info("Isolated memory database tables dropped cleanly.")

    logger.info("SUCCESS: All isolation self-check steps PASSED with 0 live database interactions.")
    return True


def run_suite(suite_filename):
    """
    Runs a specified test suite file in the isolated environment.
    """
    if os.path.isabs(suite_filename):
        suite_path = suite_filename
    else:
        suite_path = os.path.join(PROJECT_ROOT, suite_filename)
        if not os.path.isfile(suite_path):
            suite_path = os.path.abspath(suite_filename)

    if not os.path.isfile(suite_path):
        logger.error(f"Test suite file not found: {suite_filename}")
        sys.exit(1)

    logger.info(f"Preparing isolated execution of suite: {os.path.basename(suite_path)}...")
    setup_isolation(fail_closed_test=False)
    app, db, User, Person = verify_isolated_app()

    with app.app_context():
        db.create_all()

    # Load and execute test suite (works for root or subfolder paths)
    suite_dir = os.path.dirname(os.path.abspath(suite_path))
    if suite_dir not in sys.path:
        sys.path.insert(0, suite_dir)
    module_name = os.path.splitext(os.path.basename(suite_path))[0]
    import importlib
    test_module = importlib.import_module(module_name)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(test_module)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    with app.app_context():
        db.drop_all()

    sys.exit(0 if result.wasSuccessful() else 1)


def main():
    parser = argparse.ArgumentParser(description="ThirdEye Isolated Test Runner")
    parser.add_argument("--self-check", action="store_true", help="Run lightweight isolation self-check")
    parser.add_argument("--fail-closed-test", action="store_true", help="Test runner fail-closed defense (must exit 101)")
    parser.add_argument("--suite", type=str, help="Run an individually selected test suite file")

    args = parser.parse_args()

    if args.fail_closed_test:
        setup_isolation(fail_closed_test=True)
        verify_isolated_app()
        # Should never reach here if fail-closed works
        sys.exit(0)
    elif args.suite:
        run_suite(args.suite)
    else:
        # Default behavior: run the self-check
        success = run_isolation_self_check()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
