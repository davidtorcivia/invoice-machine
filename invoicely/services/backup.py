"""Backup service for database and data files."""

import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json

from invoicely.config import get_settings

settings = get_settings()


class BackupService:
    """Service for creating and managing backups."""

    def __init__(
        self,
        backup_dir: Optional[Path] = None,
        retention_days: int = 30,
        s3_config: Optional[dict] = None,
    ):
        self.backup_dir = backup_dir or settings.data_dir / "backups"
        self.retention_days = retention_days
        self.s3_config = s3_config
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, compress: bool = True) -> dict:
        """
        Create a backup of the database and return backup info.

        Returns dict with: filename, path, size_bytes, timestamp, uploaded_to_s3
        """
        timestamp = datetime.utcnow()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

        # Source database
        db_path = settings.data_dir / "invoicely.db"
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found at {db_path}")

        # Create backup filename
        if compress:
            backup_filename = f"invoicely_backup_{timestamp_str}.db.gz"
        else:
            backup_filename = f"invoicely_backup_{timestamp_str}.db"

        backup_path = self.backup_dir / backup_filename

        # Copy and optionally compress
        if compress:
            with open(db_path, "rb") as f_in:
                with gzip.open(backup_path, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(db_path, backup_path)

        size_bytes = backup_path.stat().st_size

        result = {
            "filename": backup_filename,
            "path": str(backup_path),
            "size_bytes": size_bytes,
            "timestamp": timestamp.isoformat(),
            "compressed": compress,
            "uploaded_to_s3": False,
        }

        # Upload to S3 if configured
        if self.s3_config and self.s3_config.get("enabled"):
            try:
                self._upload_to_s3(backup_path, backup_filename)
                result["uploaded_to_s3"] = True
            except Exception as e:
                result["s3_error"] = str(e)

        return result

    def _upload_to_s3(self, local_path: Path, filename: str):
        """Upload backup to S3-compatible storage."""
        import boto3
        from botocore.config import Config

        config = self.s3_config
        if not config:
            raise ValueError("S3 configuration not provided")

        # Create S3 client
        s3_client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = config.get("bucket")
        prefix = config.get("prefix", "invoice-machine-backups")
        key = f"{prefix}/{filename}"

        s3_client.upload_file(str(local_path), bucket, key)

    def list_backups(self) -> list[dict]:
        """List all local backups sorted by date (newest first)."""
        backups = []
        for path in self.backup_dir.glob("invoicely_backup_*.db*"):
            stat = path.stat()
            backups.append({
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "compressed": path.suffix == ".gz",
            })

        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    def cleanup_old_backups(self) -> int:
        """
        Delete backups older than retention_days.

        Returns number of backups deleted.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        deleted = 0

        for path in self.backup_dir.glob("invoicely_backup_*.db*"):
            stat = path.stat()
            created = datetime.fromtimestamp(stat.st_mtime)
            if created < cutoff:
                path.unlink()
                deleted += 1

        # Also cleanup S3 if configured
        if self.s3_config and self.s3_config.get("enabled"):
            try:
                deleted += self._cleanup_s3_backups(cutoff)
            except Exception:
                pass  # Don't fail if S3 cleanup fails

        return deleted

    def _cleanup_s3_backups(self, cutoff: datetime) -> int:
        """Delete old backups from S3."""
        import boto3
        from botocore.config import Config

        config = self.s3_config
        if not config:
            return 0

        s3_client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = config.get("bucket")
        prefix = config.get("prefix", "invoice-machine-backups")

        # List objects
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        deleted = 0

        for obj in response.get("Contents", []):
            if obj["LastModified"].replace(tzinfo=None) < cutoff:
                s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
                deleted += 1

        return deleted

    def validate_backup(self, backup_path: Path) -> bool:
        """
        Validate that a backup file is a valid SQLite database.

        Returns True if valid, raises exception if not.
        """
        import sqlite3
        import tempfile

        # If compressed, decompress to temp file for validation
        if backup_path.suffix == ".gz":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                tmp_path = Path(tmp.name)
            try:
                with gzip.open(backup_path, "rb") as f_in:
                    with open(tmp_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                test_path = tmp_path
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                raise ValueError(f"Failed to decompress backup: {e}")
        else:
            test_path = backup_path
            tmp_path = None

        try:
            # Try to open and query the database
            conn = sqlite3.connect(test_path)
            cursor = conn.cursor()

            # Check for expected tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            required_tables = {"users", "business_profile", "clients", "invoices", "invoice_items"}
            missing = required_tables - tables

            conn.close()

            if missing:
                raise ValueError(f"Backup is missing required tables: {missing}")

            return True
        except sqlite3.Error as e:
            raise ValueError(f"Invalid SQLite database: {e}")
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    def restore_backup(self, backup_filename: str, validate: bool = True) -> dict:
        """
        Restore database from a backup file.

        This is a graceful restore that:
        1. Validates the backup file integrity
        2. Creates a pre-restore backup of current database
        3. Performs the restore
        4. Returns information about the restore operation

        Warning: This will overwrite the current database!
        The application should be restarted after restore.
        """
        backup_path = self.backup_dir / backup_filename
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_filename}")

        # Validate backup before proceeding
        if validate:
            self.validate_backup(backup_path)

        db_path = settings.data_dir / "invoicely.db"
        pre_restore_filename = None

        # Create a backup of current database before restoring
        if db_path.exists():
            pre_restore_filename = f"pre_restore_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
            pre_restore_backup = self.backup_dir / pre_restore_filename
            shutil.copy2(db_path, pre_restore_backup)

        # Restore
        if backup_path.suffix == ".gz":
            with gzip.open(backup_path, "rb") as f_in:
                with open(db_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_path, db_path)

        return {
            "restored_from": backup_filename,
            "pre_restore_backup": pre_restore_filename,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Database restored. Please restart the application for changes to take effect.",
        }

    def download_from_s3(self, filename: str) -> Path:
        """Download a backup from S3 to local backup directory."""
        import boto3
        from botocore.config import Config

        config = self.s3_config
        if not config or not config.get("enabled"):
            raise ValueError("S3 is not configured")

        s3_client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = config.get("bucket")
        prefix = config.get("prefix", "invoice-machine-backups")
        key = f"{prefix}/{filename}"

        local_path = self.backup_dir / filename
        s3_client.download_file(bucket, key, str(local_path))

        return local_path

    def list_s3_backups(self) -> list[dict]:
        """List backups stored in S3."""
        import boto3
        from botocore.config import Config

        config = self.s3_config
        if not config or not config.get("enabled"):
            return []

        try:
            s3_client = boto3.client(
                "s3",
                endpoint_url=config.get("endpoint_url"),
                aws_access_key_id=config.get("access_key_id"),
                aws_secret_access_key=config.get("secret_access_key"),
                region_name=config.get("region", "auto"),
                config=Config(signature_version="s3v4"),
            )

            bucket = config.get("bucket")
            prefix = config.get("prefix", "invoice-machine-backups")

            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            backups = []

            for obj in response.get("Contents", []):
                filename = obj["Key"].split("/")[-1]
                if filename.startswith("invoicely_backup_"):
                    backups.append({
                        "filename": filename,
                        "size_bytes": obj["Size"],
                        "created_at": obj["LastModified"].isoformat(),
                        "location": "s3",
                    })

            backups.sort(key=lambda x: x["created_at"], reverse=True)
            return backups
        except Exception:
            return []

    def delete_backup(self, backup_filename: str) -> bool:
        """Delete a specific backup file."""
        backup_path = self.backup_dir / backup_filename
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False


def get_backup_service(
    retention_days: Optional[int] = None,
    s3_config: Optional[dict] = None,
) -> BackupService:
    """Get a BackupService instance with optional configuration."""
    return BackupService(
        retention_days=retention_days or 30,
        s3_config=s3_config,
    )
