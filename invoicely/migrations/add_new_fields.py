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
        # Backup settings
        ("business_profile", "backup_enabled", "INTEGER DEFAULT 1"),
        ("business_profile", "backup_retention_days", "INTEGER DEFAULT 30"),
        ("business_profile", "backup_s3_enabled", "INTEGER DEFAULT 0"),
        ("business_profile", "backup_s3_config", "TEXT"),
        # Invoice fields
        ("invoices", "document_type", "VARCHAR(20) DEFAULT 'invoice'"),
        ("invoices", "client_reference", "VARCHAR(100)"),
        ("invoices", "show_payment_instructions", "INTEGER DEFAULT 1"),
        ("invoices", "selected_payment_methods", "TEXT"),
        # InvoiceItem fields
        ("invoice_items", "unit_type", "VARCHAR(10) DEFAULT 'qty'"),
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
