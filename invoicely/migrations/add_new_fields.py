"""Migration script to add new fields for Invoice Machine features.

Run with: python -m invoicely.migrations.add_new_fields
"""

import sqlite3
import sys
from pathlib import Path

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "invoicely.db"


def migrate(db_path: Path = DEFAULT_DB_PATH):
    """Add new columns to existing tables."""
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Database will be created with new schema on first run.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Helper to check if column exists
    def column_exists(table: str, column: str) -> bool:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        return column in columns

    migrations = [
        # BusinessProfile fields
        ("business_profile", "default_payment_instructions", "TEXT"),
        ("business_profile", "payment_methods", "TEXT"),
        ("business_profile", "theme_preference", "VARCHAR(20) DEFAULT 'system'"),
        ("business_profile", "mcp_api_key", "VARCHAR(64)"),
        ("business_profile", "app_base_url", "VARCHAR(500)"),
        ("business_profile", "default_currency_code", "VARCHAR(3) DEFAULT 'USD'"),
        # Backup settings
        ("business_profile", "backup_enabled", "INTEGER DEFAULT 1"),
        ("business_profile", "backup_retention_days", "INTEGER DEFAULT 30"),
        ("business_profile", "backup_s3_enabled", "INTEGER DEFAULT 0"),
        ("business_profile", "backup_s3_config", "TEXT"),
        # Tax settings (optional - disabled by default)
        ("business_profile", "default_tax_enabled", "INTEGER DEFAULT 0"),
        ("business_profile", "default_tax_rate", "DECIMAL(5,2) DEFAULT 0.00"),
        ("business_profile", "default_tax_name", "VARCHAR(50) DEFAULT 'Tax'"),
        # SMTP settings (optional - user must configure to enable email)
        ("business_profile", "smtp_enabled", "INTEGER DEFAULT 0"),
        ("business_profile", "smtp_host", "VARCHAR(255)"),
        ("business_profile", "smtp_port", "INTEGER DEFAULT 587"),
        ("business_profile", "smtp_username", "VARCHAR(255)"),
        ("business_profile", "smtp_password", "VARCHAR(255)"),
        ("business_profile", "smtp_from_email", "VARCHAR(255)"),
        ("business_profile", "smtp_from_name", "VARCHAR(255)"),
        ("business_profile", "smtp_use_tls", "INTEGER DEFAULT 1"),
        # Email template settings
        ("business_profile", "email_subject_template", "VARCHAR(500)"),
        ("business_profile", "email_body_template", "TEXT"),
        # Invoice fields
        ("invoices", "document_type", "VARCHAR(20) DEFAULT 'invoice'"),
        ("invoices", "client_reference", "VARCHAR(100)"),
        ("invoices", "show_payment_instructions", "INTEGER DEFAULT 1"),
        ("invoices", "selected_payment_methods", "TEXT"),
        # Invoice tax fields (optional - disabled by default)
        ("invoices", "tax_enabled", "INTEGER DEFAULT 0"),
        ("invoices", "tax_rate", "DECIMAL(5,2) DEFAULT 0.00"),
        ("invoices", "tax_name", "VARCHAR(50) DEFAULT 'Tax'"),
        ("invoices", "tax_amount", "DECIMAL(10,2) DEFAULT 0.00"),
        # InvoiceItem fields
        ("invoice_items", "unit_type", "VARCHAR(10) DEFAULT 'qty'"),
        # Client tax settings (per-client override, NULL = use global default)
        ("clients", "tax_enabled", "INTEGER"),
        ("clients", "tax_rate", "DECIMAL(5,2)"),
        ("clients", "tax_name", "VARCHAR(50)"),
        # Client currency preference (added in migration 005)
        ("clients", "preferred_currency", "VARCHAR(3)"),
    ]

    for table, column, col_type in migrations:
        if not column_exists(table, column):
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                print(f"Added {table}.{column}")
            except sqlite3.OperationalError as e:
                print(f"Error adding {table}.{column}: {e}")
        else:
            print(f"Column {table}.{column} already exists")

    conn.commit()
    conn.close()
    print("Migration completed successfully!")


if __name__ == "__main__":
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    migrate(db_path)
