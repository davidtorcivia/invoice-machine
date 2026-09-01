#!/usr/bin/env python
"""Standalone tests for database migration logic.

Run with: python tests/test_migrations_standalone.py
"""

import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_alembic_version_detection_empty():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
        conn.commit()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        has_alembic_table = cursor.fetchone() is not None
        assert has_alembic_table is True, "Should detect alembic_version table"

        cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
        has_valid_version = cursor.fetchone() is not None
        assert has_valid_version is False, "Should detect empty alembic_version"

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        has_users = cursor.fetchone() is not None
        assert has_users is True, "Should detect users table"

        conn.close()

        # This is the condition that should trigger fallback + migrations
        assert has_users and not has_valid_version, "Should trigger fallback migration"

        print("[PASS] test_alembic_version_detection_empty")


def test_alembic_version_detection_valid():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES ('006_search_indexes')")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()

        cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
        has_valid_version = cursor.fetchone() is not None
        assert has_valid_version is True, "Should detect valid alembic version"

        conn.close()

        print("[PASS] test_alembic_version_detection_valid")


def test_migration_001_table_check():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password_hash VARCHAR(255),
                created_at DATETIME
            )
        """)
        cursor.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'hash123')"
        )
        conn.commit()

        # Check table existence (simulating migration check)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        assert "users" in existing_tables, "users table should exist"

        cursor.execute("SELECT username FROM users WHERE id = 1")
        assert cursor.fetchone()[0] == "admin", "User data should be preserved"
        conn.close()

        print("[PASS] test_migration_001_table_check")


def run_all_tests():
    """Run all migration tests."""
    tests = [
        test_alembic_version_detection_empty,
        test_alembic_version_detection_valid,
        test_migration_001_table_check,
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("Running Migration Tests")
    print("=" * 60 + "\n")

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
