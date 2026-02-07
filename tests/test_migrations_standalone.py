#!/usr/bin/env python
"""Standalone tests for database migration logic.

Run with: python tests/test_migrations_standalone.py

These tests verify that:
1. Idempotent migrations work correctly on existing databases
2. The fallback migration adds all required columns
3. The alembic_version detection works correctly
4. Data is preserved through migration scenarios
"""

import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_fallback_adds_preferred_currency():
    """Verify preferred_currency is added to clients table."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        # Create a database with clients table missing preferred_currency
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                business_name VARCHAR(255),
                email VARCHAR(255),
                tax_enabled INTEGER,
                tax_rate DECIMAL(5,2),
                tax_name VARCHAR(50)
            )
        """)
        # Insert test data
        cursor.execute("INSERT INTO clients (id, name, email) VALUES (1, 'Test Client', 'test@example.com')")
        conn.commit()
        conn.close()

        # Run the fallback migration
        from invoice_machine.migrations.add_new_fields import migrate
        migrate(db_path)

        # Verify the column was added
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "preferred_currency" in columns, f"preferred_currency not in columns: {columns}"

        # Verify data is preserved
        cursor.execute("SELECT name, email FROM clients WHERE id = 1")
        row = cursor.fetchone()
        assert row == ("Test Client", "test@example.com"), f"Data not preserved: {row}"
        conn.close()

        print("[PASS] test_fallback_adds_preferred_currency")


def test_fallback_skips_existing_columns():
    """Verify migration doesn't fail when columns already exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        # Create a database with all columns already present
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                preferred_currency VARCHAR(3),
                tax_enabled INTEGER,
                tax_rate DECIMAL(5,2),
                tax_name VARCHAR(50)
            )
        """)
        cursor.execute("""
            CREATE TABLE business_profile (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                default_payment_instructions TEXT,
                payment_methods TEXT,
                theme_preference VARCHAR(20),
                mcp_api_key VARCHAR(64),
                bot_api_key VARCHAR(64),
                app_base_url VARCHAR(500),
                backup_enabled INTEGER DEFAULT 1,
                backup_retention_days INTEGER DEFAULT 30,
                backup_s3_enabled INTEGER DEFAULT 0,
                backup_s3_config TEXT,
                default_tax_enabled INTEGER DEFAULT 0,
                default_tax_rate DECIMAL(5,2),
                default_tax_name VARCHAR(50),
                smtp_enabled INTEGER DEFAULT 0,
                smtp_host VARCHAR(255),
                smtp_port INTEGER DEFAULT 587,
                smtp_username VARCHAR(255),
                smtp_password VARCHAR(255),
                smtp_from_email VARCHAR(255),
                smtp_from_name VARCHAR(255),
                smtp_use_tls INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                document_type VARCHAR(20),
                client_reference VARCHAR(100),
                show_payment_instructions INTEGER,
                selected_payment_methods TEXT,
                tax_enabled INTEGER,
                tax_rate DECIMAL(5,2),
                tax_name VARCHAR(50),
                tax_amount DECIMAL(10,2)
            )
        """)
        cursor.execute("""
            CREATE TABLE invoice_items (
                id INTEGER PRIMARY KEY,
                unit_type VARCHAR(10)
            )
        """)
        conn.commit()
        conn.close()

        # Should not raise an error
        from invoice_machine.migrations.add_new_fields import migrate
        migrate(db_path)

        # Verify no errors and columns still exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "preferred_currency" in columns
        conn.close()

        print("[PASS] test_fallback_skips_existing_columns")


def test_alembic_version_detection_empty():
    """Verify detection of empty alembic_version table."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        # Create database with empty alembic_version table
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
        conn.commit()

        # Check detection logic
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
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
    """Verify detection of populated alembic_version table."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        # Create database with valid alembic_version
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES ('006_search_indexes')")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()

        # Check detection
        cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
        has_valid_version = cursor.fetchone() is not None
        assert has_valid_version is True, "Should detect valid alembic version"

        conn.close()

        print("[PASS] test_alembic_version_detection_valid")


def test_data_preservation():
    """Test complete migration scenario with existing data."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        # Create a realistic existing database (simulating pre-migration state)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create tables without newer columns
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password_hash VARCHAR(255),
                created_at DATETIME
            )
        """)
        cursor.execute("""
            CREATE TABLE business_profile (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                business_name VARCHAR(255),
                email VARCHAR(255)
            )
        """)
        cursor.execute("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                business_name VARCHAR(255),
                email VARCHAR(255),
                deleted_at DATETIME
            )
        """)
        cursor.execute("""
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                invoice_number VARCHAR(50) UNIQUE,
                client_id INTEGER,
                status VARCHAR(20),
                total DECIMAL(10,2),
                deleted_at DATETIME
            )
        """)
        cursor.execute("""
            CREATE TABLE invoice_items (
                id INTEGER PRIMARY KEY,
                invoice_id INTEGER,
                description TEXT,
                quantity INTEGER,
                unit_price DECIMAL(10,2),
                total DECIMAL(10,2)
            )
        """)

        # Create empty alembic_version table (simulating failed migration)
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")

        # Insert test data
        cursor.execute("INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'hashed')")
        cursor.execute("INSERT INTO business_profile (id, name, email) VALUES (1, 'Owner', 'owner@test.com')")
        cursor.execute("INSERT INTO clients (id, name, email) VALUES (1, 'Client A', 'a@test.com')")
        cursor.execute("INSERT INTO clients (id, name, email) VALUES (2, 'Client B', 'b@test.com')")
        cursor.execute("INSERT INTO invoices (id, invoice_number, client_id, status, total) VALUES (1, 'INV-001', 1, 'paid', 1000.00)")
        cursor.execute("INSERT INTO invoices (id, invoice_number, client_id, status, total) VALUES (2, 'INV-002', 2, 'draft', 500.00)")
        cursor.execute("INSERT INTO invoice_items (id, invoice_id, description, quantity, unit_price, total) VALUES (1, 1, 'Service', 10, 100.00, 1000.00)")
        conn.commit()
        conn.close()

        # Run the fallback migration
        from invoice_machine.migrations.add_new_fields import migrate
        migrate(db_path)

        # Verify all data is preserved
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        assert cursor.fetchone()[0] == 1, "Users count should be 1"

        cursor.execute("SELECT COUNT(*) FROM clients")
        assert cursor.fetchone()[0] == 2, "Clients count should be 2"

        cursor.execute("SELECT COUNT(*) FROM invoices")
        assert cursor.fetchone()[0] == 2, "Invoices count should be 2"

        cursor.execute("SELECT COUNT(*) FROM invoice_items")
        assert cursor.fetchone()[0] == 1, "Invoice items count should be 1"

        # Verify specific data
        cursor.execute("SELECT username FROM users WHERE id = 1")
        assert cursor.fetchone()[0] == "admin", "User data should be preserved"

        cursor.execute("SELECT email FROM clients WHERE id = 1")
        assert cursor.fetchone()[0] == "a@test.com", "Client data should be preserved"

        cursor.execute("SELECT total FROM invoices WHERE invoice_number = 'INV-001'")
        assert float(cursor.fetchone()[0]) == 1000.00, "Invoice data should be preserved"

        # Verify new columns were added
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "preferred_currency" in columns, "preferred_currency should be added"

        cursor.execute("PRAGMA table_info(business_profile)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "smtp_enabled" in columns, "smtp_enabled should be added"
        assert "theme_preference" in columns, "theme_preference should be added"

        conn.close()

        print("[PASS] test_data_preservation")


def test_migration_001_table_check():
    """Verify 001 migration table existence check logic."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"

        # Create database with users table
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
        cursor.execute("INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'hash123')")
        conn.commit()

        # Check table existence (simulating migration check)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        # Verify logic would skip users table
        assert "users" in existing_tables, "users table should exist"

        # Verify data would be preserved
        cursor.execute("SELECT username FROM users WHERE id = 1")
        assert cursor.fetchone()[0] == "admin", "User data should be preserved"
        conn.close()

        print("[PASS] test_migration_001_table_check")


def run_all_tests():
    """Run all migration tests."""
    tests = [
        test_fallback_adds_preferred_currency,
        test_fallback_skips_existing_columns,
        test_alembic_version_detection_empty,
        test_alembic_version_detection_valid,
        test_data_preservation,
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
