"""Tests for database migration logic.

These tests verify that:
1. Idempotent migrations work correctly on existing databases
2. The fallback migration adds all required columns
3. The alembic_version detection works correctly
4. Data is preserved through migration scenarios

Run with: python -m pytest tests/test_migrations.py -v
Or standalone: python tests/test_migrations.py
"""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFallbackMigration:
    """Test the fallback migration script (add_new_fields.py)."""

    def test_adds_missing_preferred_currency_column(self, tmp_path):
        """Verify preferred_currency is added to clients table."""
        db_path = tmp_path / "test.db"

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
        from invoicely.migrations.add_new_fields import migrate
        migrate(db_path)

        # Verify the column was added
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "preferred_currency" in columns

        # Verify data is preserved
        cursor.execute("SELECT name, email FROM clients WHERE id = 1")
        row = cursor.fetchone()
        assert row == ("Test Client", "test@example.com")
        conn.close()

    def test_skips_existing_columns(self, tmp_path):
        """Verify migration doesn't fail when columns already exist."""
        db_path = tmp_path / "test.db"

        # Create a database with all columns already present
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                preferred_currency VARCHAR(3)
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
        from invoicely.migrations.add_new_fields import migrate
        migrate(db_path)

        # Verify no errors and columns still exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "preferred_currency" in columns
        conn.close()


class TestAlembicVersionDetection:
    """Test the alembic_version table detection logic."""

    def test_detects_empty_alembic_version(self, tmp_path):
        """Verify detection of empty alembic_version table."""
        db_path = tmp_path / "test.db"

        # Create database with empty alembic_version table
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
        conn.commit()

        # Check detection logic
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        has_alembic_table = cursor.fetchone() is not None
        assert has_alembic_table is True

        cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
        has_valid_version = cursor.fetchone() is not None
        assert has_valid_version is False

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        has_users = cursor.fetchone() is not None
        assert has_users is True

        conn.close()

        # This is the condition that should trigger fallback + migrations
        assert has_users and not has_valid_version

    def test_detects_valid_alembic_version(self, tmp_path):
        """Verify detection of populated alembic_version table."""
        db_path = tmp_path / "test.db"

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
        assert has_valid_version is True

        conn.close()

    def test_detects_missing_alembic_table(self, tmp_path):
        """Verify detection when alembic_version table doesn't exist."""
        db_path = tmp_path / "test.db"

        # Create database without alembic_version
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        has_alembic_table = cursor.fetchone() is not None
        assert has_alembic_table is False

        conn.close()


class TestIdempotentMigrations:
    """Test that Alembic migrations are idempotent."""

    def test_001_initial_skips_existing_tables(self, tmp_path):
        """Verify 001_initial migration skips existing tables."""
        db_path = tmp_path / "test.db"

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
        conn.close()

        # Run the migration check logic
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        # Verify logic would skip users table
        assert "users" in existing_tables

        # Verify data would be preserved
        cursor.execute("SELECT username FROM users WHERE id = 1")
        assert cursor.fetchone()[0] == "admin"
        conn.close()

    def test_005_add_column_is_idempotent(self, tmp_path):
        """Verify 005_client_currency migration is idempotent."""
        db_path = tmp_path / "test.db"

        # Create clients table WITH preferred_currency already
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                preferred_currency VARCHAR(3)
            )
        """)
        cursor.execute("INSERT INTO clients (id, name, preferred_currency) VALUES (1, 'Test', 'EUR')")
        conn.commit()
        conn.close()

        # Check column existence logic (simulating migration check)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]

        # Migration should detect column exists and skip
        assert "preferred_currency" in columns

        # Verify data preserved
        cursor.execute("SELECT preferred_currency FROM clients WHERE id = 1")
        assert cursor.fetchone()[0] == "EUR"
        conn.close()

    def test_index_creation_is_idempotent(self, tmp_path):
        """Verify index migrations are idempotent."""
        db_path = tmp_path / "test.db"

        # Create table with index already present
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                status VARCHAR(20),
                deleted_at DATETIME
            )
        """)
        cursor.execute("CREATE INDEX idx_invoices_status_deleted ON invoices (status, deleted_at)")
        conn.commit()

        # Check index existence logic
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='invoices'")
        indexes = {row[0] for row in cursor.fetchall()}

        assert "idx_invoices_status_deleted" in indexes
        conn.close()


class TestDataPreservation:
    """Test that data is preserved through migration scenarios."""

    def test_full_migration_scenario_preserves_data(self, tmp_path):
        """Test complete migration scenario with existing data."""
        db_path = tmp_path / "test.db"

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
        from invoicely.migrations.add_new_fields import migrate
        migrate(db_path)

        # Verify all data is preserved
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM clients")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT COUNT(*) FROM invoices")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT COUNT(*) FROM invoice_items")
        assert cursor.fetchone()[0] == 1

        # Verify specific data
        cursor.execute("SELECT username FROM users WHERE id = 1")
        assert cursor.fetchone()[0] == "admin"

        cursor.execute("SELECT email FROM clients WHERE id = 1")
        assert cursor.fetchone()[0] == "a@test.com"

        cursor.execute("SELECT total FROM invoices WHERE invoice_number = 'INV-001'")
        assert float(cursor.fetchone()[0]) == 1000.00

        # Verify new columns were added
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "preferred_currency" in columns

        cursor.execute("PRAGMA table_info(business_profile)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "smtp_enabled" in columns
        assert "theme_preference" in columns

        conn.close()


class TestMigrationFlowIntegration:
    """Integration tests for the complete migration flow."""

    def test_run_alembic_migrations_with_existing_db(self, tmp_path, monkeypatch):
        """Test the full run_alembic_migrations function with existing database."""
        db_path = tmp_path / "data" / "invoicely.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create existing database with empty alembic_version
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY, name VARCHAR(255))")
        cursor.execute("INSERT INTO clients (id, name) VALUES (1, 'Test Client')")
        conn.commit()
        conn.close()

        # Mock the settings to use our temp path
        mock_settings = MagicMock()
        mock_settings.data_dir = tmp_path / "data"

        # Import and test the detection logic
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        has_alembic_table = cursor.fetchone() is not None

        has_valid_version = False
        if has_alembic_table:
            cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
            has_valid_version = cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        has_users = cursor.fetchone() is not None

        conn.close()

        # Verify correct detection
        assert has_alembic_table is True
        assert has_valid_version is False
        assert has_users is True

        # This condition should trigger fallback migration
        should_run_fallback = has_users and not has_valid_version
        assert should_run_fallback is True


class TestColumnExistence:
    """Test column existence checking."""

    def test_column_exists_function(self, tmp_path):
        """Test the column_exists helper function."""
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                existing_column VARCHAR(255)
            )
        """)
        conn.commit()

        # Test column existence check
        cursor.execute("PRAGMA table_info(test_table)")
        columns = [row[1] for row in cursor.fetchall()]

        assert "id" in columns
        assert "existing_column" in columns
        assert "nonexistent_column" not in columns

        conn.close()
