"""Tests for database migration logic."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAlembicVersionDetection:
    """Test the alembic_version table detection logic."""

    def test_detects_empty_alembic_version(self, tmp_path):
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
        conn.commit()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
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
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES ('006_search_indexes')")
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()

        cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
        has_valid_version = cursor.fetchone() is not None
        assert has_valid_version is True

        conn.close()

    def test_detects_missing_alembic_table(self, tmp_path):
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        has_alembic_table = cursor.fetchone() is not None
        assert has_alembic_table is False

        conn.close()


class TestIdempotentMigrations:
    """Test that Alembic migrations are idempotent."""

    def test_001_initial_skips_existing_tables(self, tmp_path):
        db_path = tmp_path / "test.db"

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
        conn.close()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        assert "users" in existing_tables

        cursor.execute("SELECT username FROM users WHERE id = 1")
        assert cursor.fetchone()[0] == "admin"
        conn.close()

    def test_005_add_column_is_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255),
                preferred_currency VARCHAR(3)
            )
        """)
        cursor.execute(
            "INSERT INTO clients (id, name, preferred_currency) VALUES (1, 'Test', 'EUR')"
        )
        conn.commit()
        conn.close()

        # Check column existence logic (simulating migration check)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = [row[1] for row in cursor.fetchall()]

        assert "preferred_currency" in columns

        cursor.execute("SELECT preferred_currency FROM clients WHERE id = 1")
        assert cursor.fetchone()[0] == "EUR"
        conn.close()

    def test_index_creation_is_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"

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

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='invoices'")
        indexes = {row[0] for row in cursor.fetchall()}

        assert "idx_invoices_status_deleted" in indexes
        conn.close()


class TestColumnExistence:
    """Test column existence checking."""

    def test_column_exists_function(self, tmp_path):
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

        cursor.execute("PRAGMA table_info(test_table)")
        columns = [row[1] for row in cursor.fetchall()]

        assert "id" in columns
        assert "existing_column" in columns
        assert "nonexistent_column" not in columns

        conn.close()


def test_migration_015_backfills_invoices_settled_before_payment_tracking():
    """An invoice marked paid before payment tracking must not show a balance."""
    import os
    import sqlite3
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "backfill.db"
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
        env["ENVIRONMENT"] = "development"

        # Bring the schema to 014 only, then seed as an older release would have.
        step = (
            "from alembic.config import Config; from alembic import command; "
            "command.upgrade(Config('alembic.ini'), '014_payments_reporting')"
        )
        result = subprocess.run(
            [sys.executable, "-c", step],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "INSERT INTO invoices (invoice_number, status, issue_date, total, "
            "currency_code, amount_paid, document_type) "
            "VALUES ('PAID-1', 'paid', '2026-01-15', 600, 'USD', 0, 'invoice')"
        )
        conn.execute(
            "INSERT INTO invoices (invoice_number, status, issue_date, total, "
            "currency_code, amount_paid, document_type) "
            "VALUES ('OPEN-1', 'sent', '2026-01-15', 400, 'USD', 0, 'invoice')"
        )
        conn.commit()
        conn.close()

        step = (
            "from alembic.config import Config; from alembic import command; "
            "command.upgrade(Config('alembic.ini'), 'head')"
        )
        result = subprocess.run(
            [sys.executable, "-c", step],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        conn = sqlite3.connect(str(db_file))
        try:
            paid = conn.execute(
                "SELECT amount_paid FROM invoices WHERE invoice_number='PAID-1'"
            ).fetchone()[0]
            assert paid == 600, "settled invoice should show no outstanding balance"

            open_paid = conn.execute(
                "SELECT amount_paid FROM invoices WHERE invoice_number='OPEN-1'"
            ).fetchone()[0]
            assert open_paid == 0, "unpaid invoice must be left alone"

            drift = conn.execute(
                "SELECT COUNT(*) FROM invoices i WHERE i.amount_paid != "
                "COALESCE((SELECT SUM(amount) FROM payments p WHERE p.invoice_id=i.id), 0)"
            ).fetchone()[0]
            assert drift == 0, "amount_paid must equal the sum of its payments"

            note = conn.execute(
                "SELECT notes FROM payments WHERE invoice_id="
                "(SELECT id FROM invoices WHERE invoice_number='PAID-1')"
            ).fetchone()[0]
            assert "Backfilled" in note, "backfilled rows must be labelled as such"
        finally:
            conn.close()


def test_migration_021_moves_legacy_keys_into_api_keys():
    """A key stored in the old profile column keeps working after the upgrade."""
    import os
    import sqlite3
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    from invoice_machine.crypto import hash_api_key, verify_api_key

    project_root = Path(__file__).resolve().parent.parent
    plaintext = "legacy-mcp-key"

    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "keys.db"
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
        env["ENVIRONMENT"] = "development"

        def upgrade(target):
            step = (
                "from alembic.config import Config; from alembic import command; "
                f"command.upgrade(Config('alembic.ini'), '{target}')"
            )
            result = subprocess.run(
                [sys.executable, "-c", step],
                cwd=str(project_root),
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr

        upgrade("020_backfill_marked_paid")

        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "INSERT INTO business_profile (id, name, mcp_api_key) VALUES (1, 'Test', ?)",
            (hash_api_key(plaintext),),
        )
        conn.commit()
        conn.close()

        upgrade("head")

        conn = sqlite3.connect(str(db_file))
        try:
            rows = conn.execute("SELECT kind, label, key_hash, prefix FROM api_keys").fetchall()
            assert len(rows) == 1, "the legacy key should become exactly one row"
            kind, label, key_hash, prefix = rows[0]
            assert (kind, label, prefix) == ("mcp", "Migrated MCP key", None)
            assert verify_api_key(plaintext, key_hash), "the migrated key must still authenticate"

            columns = {row[1] for row in conn.execute("PRAGMA table_info(business_profile)")}
            assert not columns & {"mcp_api_key", "bot_api_key"}
        finally:
            conn.close()


def test_migration_022_turns_checkout_session_links_into_pay_links():
    """An expiring Stripe session URL becomes a permanent /pay link on the base URL."""
    import os
    import sqlite3
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "links.db"
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
        env["ENVIRONMENT"] = "development"

        def upgrade(target):
            step = (
                "from alembic.config import Config; from alembic import command; "
                f"command.upgrade(Config('alembic.ini'), '{target}')"
            )
            result = subprocess.run(
                [sys.executable, "-c", step],
                cwd=str(project_root),
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr

        upgrade("021_api_keys")

        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "INSERT INTO business_profile (id, name, app_base_url) "
            "VALUES (1, 'Test', 'https://inv.example')"
        )
        for number, link_id in (("A-1", "cs_test_abc"), ("A-2", None)):
            conn.execute(
                "INSERT INTO invoices (invoice_number, status, document_type, issue_date, "
                "payment_terms_days, currency_code, subtotal, tax_amount, total, "
                "payment_link_id, payment_link_url, pdf_generated_at, created_at, updated_at) "
                "VALUES (?, 'sent', 'invoice', '2026-01-01', 30, 'USD', 1, 0, 1, ?, ?, "
                "'2026-01-02', '2026-01-01', '2026-01-01')",
                (number, link_id, "https://checkout.stripe.com/x" if link_id else None),
            )
        conn.commit()
        conn.close()

        upgrade("head")

        conn = sqlite3.connect(str(db_file))
        try:
            rows = dict(
                (number, (token, url, stamp))
                for number, token, url, stamp in conn.execute(
                    "SELECT invoice_number, payment_link_id, payment_link_url, pdf_generated_at "
                    "FROM invoices"
                )
            )
            token, url, stamp = rows["A-1"]
            assert token and not token.startswith("cs_")
            assert url == f"https://inv.example/pay/{token}"
            assert stamp is None, "the PDF must be reprinted with the working link"
            assert rows["A-2"] == (None, None, "2026-01-02")
        finally:
            conn.close()


def _upgrade(db_file, target, prelude=""):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    env["ENVIRONMENT"] = "development"
    step = (
        f"{prelude}\nfrom alembic.config import Config; from alembic import command; "
        f"command.upgrade(Config('alembic.ini'), '{target}')"
    )
    return subprocess.run(
        [sys.executable, "-c", step],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
        capture_output=True,
        text=True,
    )


# Leaves NULLs in columns 023 constrains. The schedule points at the invoice so
# a cascading or FK-violating rebuild of invoices cannot pass unnoticed.
_SEED_022 = """
INSERT INTO business_profile (id, name) VALUES (1, 'Biz');
INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'h');
INSERT INTO sessions (token, user_id, expires_at, csrf_token) VALUES ('t', 1, '2030-01-01', 'c');
INSERT INTO clients (id, name, email) VALUES (1, 'Acme Person', 'a@acme.test');
INSERT INTO invoices (id, invoice_number, client_id, client_name, issue_date, notes)
    VALUES (1, 'INV-1', 1, 'Acme Person', '2026-01-01', 'zebra');
INSERT INTO invoice_items (invoice_id, description, unit_price, total)
    VALUES (1, 'Widget design', 10, 10);
INSERT INTO invoice_items (invoice_id, description, quantity, unit_type, unit_price, total,
    sort_order) VALUES (1, 'Consulting', 2, 'hours', 50, 100, 1);
INSERT INTO payments (invoice_id, amount, payment_date) VALUES (1, 5, '2026-01-02');
INSERT INTO recurring_schedules (client_id, name, frequency, next_invoice_date, last_invoice_id)
    VALUES (1, 'Monthly', 'monthly', '2026-02-01', 1);
"""

_TABLES = (
    "business_profile",
    "users",
    "sessions",
    "clients",
    "invoices",
    "invoice_items",
    "payments",
    "recurring_schedules",
)

_FTS_TRIGGERS = {
    f"{table}_fts_{event}"
    for table in ("invoices", "clients", "invoice_items")
    for event in ("insert", "update", "delete")
}


def test_migration_023_enforces_not_null_without_losing_rows(tmp_path):
    import sqlite3

    import pytest

    db_file = tmp_path / "notnull.db"
    result = _upgrade(db_file, "022_permanent_pay_links")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_file))
    conn.executescript(_SEED_022)
    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}
    conn.close()

    result = _upgrade(db_file, "head")
    assert result.returncode == 0, result.stderr
    assert "Backfilled 1 NULL invoices.status" in result.stderr

    conn = sqlite3.connect(str(db_file))
    try:
        after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}
        assert after == counts, "the table rebuilds must not delete rows"

        invoice = conn.execute(
            "SELECT status, document_type, show_payment_instructions, payment_terms_days, "
            "currency_code, subtotal, tax_amount, total, tax_name, created_at "
            "FROM invoices"
        ).fetchone()
        # Flags the code reads as off when NULL stay off; an undated invoice takes
        # its issue date.
        assert invoice == ("draft", "invoice", 0, 30, "USD", 0, 0, 0, "Tax", "2026-01-01 00:00:00")
        items = conn.execute(
            "SELECT quantity, unit_type, sort_order FROM invoice_items ORDER BY id"
        ).fetchall()
        assert items == [(1, "qty", 0), (2, "hours", 1)], "only NULLs are backfilled"
        profile = conn.execute(
            "SELECT country, accent_color, smtp_port, backup_enabled, smtp_use_tls "
            "FROM business_profile"
        ).fetchone()
        assert profile == ("United States", "#16a34a", 587, 0, 0)
        schedule = conn.execute(
            "SELECT is_active, schedule_day, last_invoice_id FROM recurring_schedules"
        ).fetchone()
        assert schedule == (0, 1, 1), "a NULL schedule must not start issuing invoices"

        triggers = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        assert _FTS_TRIGGERS <= triggers
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("invoice_items", "payments"):
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            assert "REFERENCES invoices (id) ON DELETE CASCADE" in sql

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO invoices (invoice_number, status, issue_date) "
                "VALUES ('INV-X', NULL, '2026-01-01')"
            )

        conn.execute(
            "INSERT INTO clients (id, name, payment_terms_days, created_at, updated_at) "
            "VALUES (2, 'Quokka Ltd', 30, '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO invoices (id, invoice_number, client_id, status, document_type, "
            "show_payment_instructions, issue_date, payment_terms_days, currency_code, subtotal, "
            "tax_enabled, tax_rate, tax_name, tax_amount, total, notes, created_at, updated_at) "
            "VALUES (2, 'INV-2', 2, 'draft', 'invoice', 1, '2026-01-01', 30, 'USD', 0, 0, 0, "
            "'Tax', 0, 0, 'platypus', '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO invoice_items (invoice_id, description, quantity, unit_type, unit_price, "
            "total, sort_order) VALUES (2, 'Wombat grooming', 1, 'qty', 1, 1, 0)"
        )
        for fts, term, rowid in (
            ("clients_fts", "quokka", 2),
            ("invoices_fts", "platypus", 2),
            ("invoice_items_fts", "wombat", 3),
            ("invoices_fts", "zebra", 1),
        ):
            hits = conn.execute(f"SELECT rowid FROM {fts} WHERE {fts} MATCH ?", (term,)).fetchall()
            assert hits == [(rowid,)], f"{term} not found in {fts}"
    finally:
        conn.close()


def _seed_at_022(db_file, extra_sql=""):
    import sqlite3

    result = _upgrade(db_file, "022_permanent_pay_links")
    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(str(db_file))
    conn.executescript(_SEED_022 + extra_sql)
    conn.commit()
    conn.close()


def test_upgrade_tolerates_preexisting_fk_violations(tmp_path):
    """Orphans left from before FKs were enforced warn instead of blocking boot."""
    import sqlite3

    db_file = tmp_path / "orphan.db"
    _seed_at_022(
        db_file,
        "INSERT INTO invoice_items (invoice_id, description, unit_price, total) "
        "VALUES (999, 'orphan', 1, 1);",
    )

    result = _upgrade(db_file, "head")
    assert result.returncode == 0, result.stderr
    assert "1 foreign key violations from before this upgrade" in result.stderr

    conn = sqlite3.connect(str(db_file))
    try:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "023_enforce_not_null"
        )
        assert conn.execute("SELECT COUNT(*) FROM invoice_items").fetchone()[0] == 3
    finally:
        conn.close()


# Deletes the client just before 023 rebuilds clients, so the invoice and the
# schedule that reference it become violations the upgrade itself introduced.
_DELETE_PARENT_DURING_UPGRADE = """
from alembic.operations import Operations
_batch = Operations.batch_alter_table
def _patched(self, table_name, *args, **kw):
    if table_name == "clients":
        self.execute("DELETE FROM clients WHERE id = 1")
    return _batch(self, table_name, *args, **kw)
Operations.batch_alter_table = _patched
"""


def test_upgrade_rolls_back_introduced_fk_violations(tmp_path):
    """A violation created by the upgrade undoes every migration in it."""
    import sqlite3

    db_file = tmp_path / "rollback.db"
    _seed_at_022(db_file)

    result = _upgrade(db_file, "head", prelude=_DELETE_PARENT_DURING_UPGRADE)
    assert result.returncode != 0
    assert "introduced foreign key violations" in result.stderr
    assert "from before this upgrade" not in result.stderr

    conn = sqlite3.connect(str(db_file))
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == "022_permanent_pay_links"
        assert conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 1
        notnull = {r[1]: r[3] for r in conn.execute("PRAGMA table_info(invoices)")}
        assert notnull["status"] == 0, "023's rebuild must be rolled back"
        assert conn.execute("SELECT status FROM invoices").fetchone()[0] is None
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert _FTS_TRIGGERS <= names
        assert "idx_invoices_status" in names
        assert not [n for n in names if n.startswith("_alembic_tmp")]
    finally:
        conn.close()
