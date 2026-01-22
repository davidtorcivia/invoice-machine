"""Tests for backup service functionality.

These tests verify:
- Local backup creation (compressed and uncompressed)
- Backup listing
- Retention cleanup
- S3 upload (mocked)
- Error handling
"""

import gzip
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from invoice_machine.services import BackupService


class TestBackupServiceInit:
    """Tests for BackupService initialization."""

    def test_init_creates_backup_dir(self):
        """Backup directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            assert not backup_dir.exists()

            service = BackupService(backup_dir=backup_dir)

            assert backup_dir.exists()
            assert service.backup_dir == backup_dir

    def test_init_custom_retention(self):
        """Custom retention days are stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir, retention_days=7)

            assert service.retention_days == 7

    def test_init_s3_config(self):
        """S3 configuration is stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            s3_config = {
                "enabled": True,
                "bucket": "my-bucket",
                "access_key_id": "key",
            }
            service = BackupService(backup_dir=backup_dir, s3_config=s3_config)

            assert service.s3_config == s3_config


class TestCreateBackup:
    """Tests for backup creation."""

    @pytest.fixture
    def mock_db_file(self):
        """Create a mock database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            db_file = data_dir / "invoice_machine.db"
            db_file.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
            yield db_file

    def test_create_backup_compressed(self, mock_db_file):
        """Create a compressed backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = mock_db_file.parent

                result = service.create_backup(compress=True)

                assert result["compressed"] is True
                assert result["filename"].endswith(".db.gz")
                assert Path(result["path"]).exists()
                assert result["size_bytes"] > 0
                assert result["uploaded_to_s3"] is False

                # Verify it's actually gzipped
                with gzip.open(result["path"], "rb") as f:
                    content = f.read()
                    assert content.startswith(b"SQLite format 3")

    def test_create_backup_uncompressed(self, mock_db_file):
        """Create an uncompressed backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = mock_db_file.parent

                result = service.create_backup(compress=False)

                assert result["compressed"] is False
                assert result["filename"].endswith(".db")
                assert not result["filename"].endswith(".db.gz")
                assert Path(result["path"]).exists()

                # Verify it's a direct copy
                content = Path(result["path"]).read_bytes()
                assert content.startswith(b"SQLite format 3")

    def test_create_backup_db_not_found(self):
        """Raise error when database doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = Path("/nonexistent")

                with pytest.raises(FileNotFoundError, match="Database not found"):
                    service.create_backup()

    def test_create_backup_with_s3_upload(self, mock_db_file):
        """Upload backup to S3 when configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            s3_config = {
                "enabled": True,
                "bucket": "test-bucket",
                "endpoint_url": "https://s3.example.com",
                "access_key_id": "test-key",
                "secret_access_key": "test-secret",
            }
            service = BackupService(backup_dir=backup_dir, s3_config=s3_config)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = mock_db_file.parent

                with patch.object(service, "_upload_to_s3") as mock_upload:
                    result = service.create_backup()

                    assert result["uploaded_to_s3"] is True
                    mock_upload.assert_called_once()

    def test_create_backup_s3_upload_failure(self, mock_db_file):
        """Handle S3 upload failure gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            s3_config = {"enabled": True, "bucket": "test-bucket"}
            service = BackupService(backup_dir=backup_dir, s3_config=s3_config)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = mock_db_file.parent

                with patch.object(
                    service, "_upload_to_s3", side_effect=Exception("S3 error")
                ):
                    result = service.create_backup()

                    # Backup should still succeed locally
                    assert Path(result["path"]).exists()
                    assert result["uploaded_to_s3"] is False
                    assert "S3 error" in result["s3_error"]

    def test_create_backup_timestamp_in_filename(self, mock_db_file):
        """Backup filename includes timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = mock_db_file.parent

                result = service.create_backup()

                # Filename should contain date/time pattern
                assert "invoice_machine_backup_" in result["filename"]
                # Should be in format YYYYMMDD_HHMMSS
                import re

                pattern = r"invoice_machine_backup_\d{8}_\d{6}\.db"
                assert re.match(pattern, result["filename"].replace(".gz", ""))


class TestListBackups:
    """Tests for backup listing."""

    def test_list_backups_empty(self):
        """List empty backup directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir)

            result = service.list_backups()

            assert result == []

    def test_list_backups_multiple(self):
        """List multiple backups sorted by date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create test backups
            old_backup = backup_dir / "invoice_machine_backup_20250101_120000.db.gz"
            old_backup.write_bytes(b"old backup")

            new_backup = backup_dir / "invoice_machine_backup_20250115_120000.db.gz"
            new_backup.write_bytes(b"new backup content")

            uncompressed = backup_dir / "invoice_machine_backup_20250110_120000.db"
            uncompressed.write_bytes(b"uncompressed")

            service = BackupService(backup_dir=backup_dir)
            result = service.list_backups()

            assert len(result) == 3
            # Check all backups are listed
            filenames = [b["filename"] for b in result]
            assert "invoice_machine_backup_20250101_120000.db.gz" in filenames
            assert "invoice_machine_backup_20250115_120000.db.gz" in filenames
            assert "invoice_machine_backup_20250110_120000.db" in filenames

    def test_list_backups_includes_metadata(self):
        """Backup listing includes metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            backup_file = backup_dir / "invoice_machine_backup_20250115_120000.db.gz"
            backup_file.write_bytes(b"test content here")

            service = BackupService(backup_dir=backup_dir)
            result = service.list_backups()

            assert len(result) == 1
            backup = result[0]
            assert backup["filename"] == "invoice_machine_backup_20250115_120000.db.gz"
            assert backup["size_bytes"] == len(b"test content here")
            assert backup["compressed"] is True
            assert "created_at" in backup

    def test_list_backups_ignores_other_files(self):
        """Only list backup files, ignore others."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create valid backup
            (backup_dir / "invoice_machine_backup_20250115_120000.db.gz").write_bytes(
                b"backup"
            )
            # Create other files that should be ignored
            (backup_dir / "random_file.txt").write_bytes(b"text")
            (backup_dir / "other_backup.db").write_bytes(b"other")

            service = BackupService(backup_dir=backup_dir)
            result = service.list_backups()

            assert len(result) == 1
            assert result[0]["filename"] == "invoice_machine_backup_20250115_120000.db.gz"


class TestS3Upload:
    """Tests for S3 upload functionality."""

    def test_upload_to_s3_no_config(self):
        """Raise error when S3 config is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            service = BackupService(backup_dir=backup_dir)

            with pytest.raises(ValueError, match="configuration not provided"):
                service._upload_to_s3(Path("/test/file"), "test.db.gz")

    def test_upload_to_s3_success(self):
        """Successfully upload to S3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            backup_file = backup_dir / "test.db.gz"
            backup_file.write_bytes(b"backup content")

            s3_config = {
                "enabled": True,
                "bucket": "test-bucket",
                "endpoint_url": "https://s3.example.com",
                "access_key_id": "key",
                "secret_access_key": "secret",
                "region": "us-east-1",
                "prefix": "backups",
            }
            service = BackupService(backup_dir=backup_dir, s3_config=s3_config)

            with patch("invoice_machine.services.boto3.client") as mock_boto:
                mock_client = MagicMock()
                mock_boto.return_value = mock_client

                service._upload_to_s3(backup_file, "test.db.gz")

                mock_client.upload_file.assert_called_once()
                call_args = mock_client.upload_file.call_args
                assert call_args[0][0] == str(backup_file)  # local path
                assert call_args[0][1] == "test-bucket"  # bucket
                assert call_args[0][2] == "backups/test.db.gz"  # key

    def test_upload_to_s3_default_prefix(self):
        """Use default prefix when not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            backup_file = backup_dir / "test.db.gz"
            backup_file.write_bytes(b"backup content")

            s3_config = {
                "enabled": True,
                "bucket": "test-bucket",
                "access_key_id": "key",
                "secret_access_key": "secret",
            }
            service = BackupService(backup_dir=backup_dir, s3_config=s3_config)

            with patch("invoice_machine.services.boto3.client") as mock_boto:
                mock_client = MagicMock()
                mock_boto.return_value = mock_client

                service._upload_to_s3(backup_file, "test.db.gz")

                call_args = mock_client.upload_file.call_args
                # Should use default prefix
                assert call_args[0][2] == "invoice-machine-backups/test.db.gz"


class TestRetentionCleanup:
    """Tests for backup retention cleanup."""

    def test_cleanup_old_backups(self):
        """Delete backups older than retention period."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create old backup (simulate old mtime)
            old_backup = backup_dir / "invoice_machine_backup_20240101_120000.db.gz"
            old_backup.write_bytes(b"old")

            # Create recent backup
            new_backup = backup_dir / "invoice_machine_backup_20250115_120000.db.gz"
            new_backup.write_bytes(b"new")

            service = BackupService(backup_dir=backup_dir, retention_days=30)

            # Mock the file modification time for old backup
            import os
            import time

            old_time = time.time() - (40 * 24 * 60 * 60)  # 40 days ago
            os.utime(old_backup, (old_time, old_time))

            deleted_count = service.cleanup_old_backups()

            assert deleted_count == 1
            assert not old_backup.exists()
            assert new_backup.exists()

    def test_cleanup_preserves_recent(self):
        """Preserve backups within retention period."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create recent backups
            for i in range(3):
                backup = backup_dir / f"invoice_machine_backup_2025011{i}_120000.db.gz"
                backup.write_bytes(b"recent")

            service = BackupService(backup_dir=backup_dir, retention_days=30)
            deleted_count = service.cleanup_old_backups()

            assert deleted_count == 0
            # All backups should still exist
            backups = list(backup_dir.glob("invoice_machine_backup_*.db.gz"))
            assert len(backups) == 3


class TestRestoreBackup:
    """Tests for backup restoration."""

    def test_restore_backup_success(self):
        """Successfully restore from backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create original database
            db_file = data_dir / "invoice_machine.db"
            db_file.write_bytes(b"original database content")

            # Create backup (uncompressed for simplicity) with valid SQLite header
            backup_content = b"SQLite format 3\x00" + b"\x00" * 100
            backup_file = backup_dir / "invoice_machine_backup_20250115_120000.db"
            backup_file.write_bytes(backup_content)

            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = data_dir

                result = service.restore_backup(
                    "invoice_machine_backup_20250115_120000.db", validate=False
                )

                assert "restored_from" in result
                assert result["restored_from"] == "invoice_machine_backup_20250115_120000.db"
                # Pre-restore backup should be created
                assert result["pre_restore_backup"] is not None
                # Database should be restored
                assert db_file.read_bytes() == backup_content

    def test_restore_compressed_backup(self):
        """Restore from compressed backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create original database
            db_file = data_dir / "invoice_machine.db"
            db_file.write_bytes(b"original")

            # Create compressed backup with valid SQLite header
            backup_content = b"SQLite format 3\x00" + b"\x00" * 100
            backup_file = backup_dir / "invoice_machine_backup_20250115_120000.db.gz"
            with gzip.open(backup_file, "wb") as f:
                f.write(backup_content)

            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = data_dir

                result = service.restore_backup(
                    "invoice_machine_backup_20250115_120000.db.gz", validate=False
                )

                assert "restored_from" in result
                assert db_file.read_bytes() == backup_content

    def test_restore_backup_not_found(self):
        """Handle missing backup file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            service = BackupService(backup_dir=backup_dir)

            with pytest.raises(FileNotFoundError, match="Backup not found"):
                service.restore_backup("nonexistent.db.gz")

    def test_restore_creates_pre_restore_backup(self):
        """Create pre-restore backup of existing database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()

            # Create original database
            db_file = data_dir / "invoice_machine.db"
            original_content = b"original database"
            db_file.write_bytes(original_content)

            # Create backup with valid SQLite header
            backup_content = b"SQLite format 3\x00" + b"\x00" * 100
            backup_file = backup_dir / "invoice_machine_backup_20250115_120000.db"
            backup_file.write_bytes(backup_content)

            service = BackupService(backup_dir=backup_dir)

            with patch("invoice_machine.services.get_settings") as mock_settings:
                mock_settings.return_value.data_dir = data_dir

                result = service.restore_backup(
                    "invoice_machine_backup_20250115_120000.db", validate=False
                )

                # Pre-restore backup should be created
                pre_restore_file = backup_dir / result["pre_restore_backup"]
                assert pre_restore_file.exists()
                assert pre_restore_file.read_bytes() == original_content
