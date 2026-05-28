"""Backup-related service operations."""

import gzip
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from botocore.config import Config

from invoice_machine.config import get_settings
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)

# Keep at most this many pre-restore safety copies (they are never age-pruned
# by retention since they are the most important recovery artifact).
_MAX_PRE_RESTORE_BACKUPS = 10

# Embedded timestamp like 20260115_120000 in backup filenames.
_BACKUP_TS_RE = re.compile(r"(\d{8}_\d{6})")


def _parse_backup_timestamp(filename: str) -> datetime | None:
    """Parse the embedded YYYYMMDD_HHMMSS timestamp from a backup filename."""
    match = _BACKUP_TS_RE.search(filename)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _snapshot_database(db_path: Path, dest_path: Path) -> None:
    """Write a transactionally-consistent copy of the SQLite DB to dest_path.

    Uses the SQLite online backup API, which is safe under WAL and concurrent
    writers (a plain file copy can capture a torn page or miss the -wal file).
    """
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest_path))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


class BackupService:
    """Service for creating and managing backups."""

    def __init__(
        self,
        backup_dir: Path | None = None,
        retention_days: int = 30,
        s3_config: dict | None = None,
    ):
        if backup_dir is None:
            backup_dir = get_settings().data_dir / "backups"
        self.backup_dir = backup_dir
        self.retention_days = retention_days
        self.s3_config = s3_config
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, compress: bool = True) -> dict:
        """Create a backup of the database and optionally upload it to S3."""
        settings = get_settings()
        timestamp = utc_now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

        db_path = settings.data_dir / "invoice_machine.db"
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found at {db_path}")

        backup_filename = (
            f"invoice_machine_backup_{timestamp_str}.db.gz"
            if compress
            else f"invoice_machine_backup_{timestamp_str}.db"
        )
        backup_path = self.backup_dir / backup_filename

        # Take a consistent snapshot first (safe under WAL/concurrent writes),
        # then compress or move it into place.
        snapshot_fd, snapshot_name = tempfile.mkstemp(suffix=".db", dir=self.backup_dir)
        os.close(snapshot_fd)
        snapshot_path = Path(snapshot_name)
        try:
            _snapshot_database(db_path, snapshot_path)
            if compress:
                with open(snapshot_path, "rb") as src, gzip.open(
                    backup_path, "wb", compresslevel=6
                ) as dst:
                    shutil.copyfileobj(src, dst)
            else:
                shutil.copy2(snapshot_path, backup_path)
        finally:
            snapshot_path.unlink(missing_ok=True)

        result = {
            "filename": backup_filename,
            "path": str(backup_path),
            "size_bytes": backup_path.stat().st_size,
            "timestamp": timestamp.isoformat(),
            "compressed": compress,
            "uploaded_to_s3": False,
        }

        if self.s3_config and self.s3_config.get("enabled"):
            try:
                self._upload_to_s3(backup_path, backup_filename)
                result["uploaded_to_s3"] = True
            except Exception as exc:
                result["s3_error"] = str(exc)

        return result

    def _upload_to_s3(self, local_path: Path, filename: str):
        """Upload a backup to S3-compatible storage."""
        if not self.s3_config:
            raise ValueError("S3 configuration not provided")

        s3_client = boto3.client(
            "s3",
            endpoint_url=self.s3_config.get("endpoint_url"),
            aws_access_key_id=self.s3_config.get("access_key_id"),
            aws_secret_access_key=self.s3_config.get("secret_access_key"),
            region_name=self.s3_config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = self.s3_config.get("bucket")
        prefix = self.s3_config.get("prefix", "invoice-machine-backups")
        s3_client.upload_file(str(local_path), bucket, f"{prefix}/{filename}")

    def list_backups(self) -> list[dict]:
        """List all local backups sorted newest first."""
        backups = []
        for pattern in ["invoice_machine_backup_*.db*", "invoicely_backup_*.db*"]:
            for path in self.backup_dir.glob(pattern):
                stat = path.stat()
                # Prefer the timestamp embedded in the filename; fall back to mtime.
                created = _parse_backup_timestamp(path.name) or datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                )
                backups.append({
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "created_at": created.isoformat(),
                    "compressed": path.suffix == ".gz",
                })

        backups.sort(key=lambda backup: backup["created_at"], reverse=True)
        return backups

    def cleanup_old_backups(self) -> int:
        """Delete local and optional S3 backups older than retention_days.

        Age is taken from the timestamp embedded in the filename (not mtime,
        which a copy/rsync/restore would reset). Pre-restore safety copies are
        capped by count rather than age.
        """
        cutoff = utc_now() - timedelta(days=self.retention_days)
        deleted = 0

        for pattern in ["invoice_machine_backup_*.db*", "invoicely_backup_*.db*"]:
            for path in self.backup_dir.glob(pattern):
                created = _parse_backup_timestamp(path.name) or datetime.fromtimestamp(
                    path.stat().st_mtime, tz=UTC
                )
                if created < cutoff:
                    path.unlink()
                    deleted += 1

        deleted += self._cleanup_pre_restore_backups()

        if self.s3_config and self.s3_config.get("enabled"):
            try:
                deleted += self._cleanup_s3_backups(cutoff)
            except Exception:
                logger.warning("S3 backup cleanup failed", exc_info=True)

        return deleted

    def _cleanup_pre_restore_backups(self) -> int:
        """Keep only the most recent _MAX_PRE_RESTORE_BACKUPS pre-restore copies."""
        pre_restore = sorted(
            self.backup_dir.glob("pre_restore_*.db"),
            key=lambda p: _parse_backup_timestamp(p.name)
            or datetime.fromtimestamp(p.stat().st_mtime, tz=UTC),
            reverse=True,
        )
        deleted = 0
        for path in pre_restore[_MAX_PRE_RESTORE_BACKUPS:]:
            path.unlink(missing_ok=True)
            deleted += 1
        return deleted

    def _cleanup_s3_backups(self, cutoff: datetime) -> int:
        """Delete old backups from S3-compatible storage."""
        if not self.s3_config:
            return 0

        s3_client = boto3.client(
            "s3",
            endpoint_url=self.s3_config.get("endpoint_url"),
            aws_access_key_id=self.s3_config.get("access_key_id"),
            aws_secret_access_key=self.s3_config.get("secret_access_key"),
            region_name=self.s3_config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = self.s3_config.get("bucket")
        prefix = self.s3_config.get("prefix", "invoice-machine-backups")
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

        deleted = 0
        for obj in response.get("Contents", []):
            if obj["LastModified"].replace(tzinfo=None) < cutoff:
                s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
                deleted += 1

        return deleted

    def validate_backup(self, backup_path: Path) -> bool:
        """Validate that a backup is a readable SQLite database."""
        if backup_path.suffix == ".gz":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                tmp_path = Path(tmp.name)
            try:
                with gzip.open(backup_path, "rb") as src, open(tmp_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                test_path = tmp_path
            except Exception as exc:
                tmp_path.unlink(missing_ok=True)
                raise ValueError(f"Failed to decompress backup: {exc}")
        else:
            test_path = backup_path
            tmp_path = None

        try:
            conn = sqlite3.connect(test_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()

            required_tables = {"users", "business_profile", "clients", "invoices", "invoice_items"}
            missing = required_tables - tables
            if missing:
                raise ValueError(f"Backup is missing required tables: {missing}")
            return True
        except sqlite3.Error as exc:
            raise ValueError(f"Invalid SQLite database: {exc}")
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    def _validate_backup_filename(self, filename: str) -> Path:
        """Validate a backup filename and keep access inside the backup directory."""
        if "/" in filename or "\\" in filename:
            raise ValueError("Invalid backup filename: path separators not allowed")
        if ".." in filename:
            raise ValueError("Invalid backup filename: parent directory reference not allowed")

        backup_path = self.backup_dir / filename
        try:
            backup_path.resolve().relative_to(self.backup_dir.resolve())
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid backup filename: {exc}")

        return backup_path

    def get_backup_path(self, backup_filename: str, must_exist: bool = True) -> Path:
        """Return a validated backup path, optionally requiring it to exist."""
        backup_path = self._validate_backup_filename(backup_filename)
        if must_exist and not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_filename}")
        return backup_path

    def restore_backup(self, backup_filename: str, validate: bool = True) -> dict:
        """Restore the database from a backup using atomic replacement."""
        settings = get_settings()
        backup_path = self.get_backup_path(backup_filename)
        if validate:
            self.validate_backup(backup_path)

        db_path = settings.data_dir / "invoice_machine.db"
        pre_restore_filename = None
        tmp_path = db_path.with_name(f"{db_path.name}.restore-{utc_now().strftime('%Y%m%d%H%M%S%f')}.tmp")

        try:
            if backup_path.suffix == ".gz":
                with gzip.open(backup_path, "rb") as src, open(tmp_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                shutil.copy2(backup_path, tmp_path)

            if db_path.exists():
                pre_restore_filename = f"pre_restore_{utc_now().strftime('%Y%m%d_%H%M%S')}.db"
                # A raw copy is correct here: the restore endpoint closes the DB
                # engine first, so WAL is checkpointed into the main file.
                shutil.copy2(db_path, self.backup_dir / pre_restore_filename)

            os.replace(tmp_path, db_path)

            # Remove stale WAL/SHM sidecars so the restored DB isn't read with
            # leftover write-ahead log data from the previous database.
            for sidecar in (
                db_path.with_name(db_path.name + "-wal"),
                db_path.with_name(db_path.name + "-shm"),
            ):
                sidecar.unlink(missing_ok=True)
        finally:
            tmp_path.unlink(missing_ok=True)

        # Keep the pre-restore copies bounded.
        self._cleanup_pre_restore_backups()

        return {
            "restored_from": backup_filename,
            "pre_restore_backup": pre_restore_filename,
            "timestamp": utc_now().isoformat(),
            "message": "Database restored. Please restart the application for changes to take effect.",
        }

    def download_from_s3(self, filename: str) -> Path:
        """Download a backup from S3-compatible storage to the local backup directory."""
        if not self.s3_config or not self.s3_config.get("enabled"):
            raise ValueError("S3 is not configured")

        local_path = self._validate_backup_filename(filename)
        s3_client = boto3.client(
            "s3",
            endpoint_url=self.s3_config.get("endpoint_url"),
            aws_access_key_id=self.s3_config.get("access_key_id"),
            aws_secret_access_key=self.s3_config.get("secret_access_key"),
            region_name=self.s3_config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = self.s3_config.get("bucket")
        prefix = self.s3_config.get("prefix", "invoice-machine-backups")
        s3_client.download_file(bucket, f"{prefix}/{filename}", str(local_path))
        return local_path

    def list_s3_backups(self) -> list[dict]:
        """List backups stored in S3-compatible storage."""
        if not self.s3_config or not self.s3_config.get("enabled"):
            return []

        try:
            s3_client = boto3.client(
                "s3",
                endpoint_url=self.s3_config.get("endpoint_url"),
                aws_access_key_id=self.s3_config.get("access_key_id"),
                aws_secret_access_key=self.s3_config.get("secret_access_key"),
                region_name=self.s3_config.get("region", "auto"),
                config=Config(signature_version="s3v4"),
            )

            bucket = self.s3_config.get("bucket")
            prefix = self.s3_config.get("prefix", "invoice-machine-backups")
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

            backups = []
            for obj in response.get("Contents", []):
                filename = obj["Key"].split("/")[-1]
                if filename.startswith("invoice_machine_backup_") or filename.startswith(
                    "invoicely_backup_"
                ):
                    backups.append({
                        "filename": filename,
                        "size_bytes": obj["Size"],
                        "created_at": obj["LastModified"].isoformat(),
                        "location": "s3",
                    })

            backups.sort(key=lambda backup: backup["created_at"], reverse=True)
            return backups
        except Exception:
            return []

    def delete_backup(self, backup_filename: str) -> bool:
        """Delete a specific local backup file."""
        backup_path = self.get_backup_path(backup_filename, must_exist=False)
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False


def get_backup_service(
    retention_days: int | None = None,
    s3_config: dict | None = None,
) -> BackupService:
    """Get a BackupService instance with optional configuration."""
    return BackupService(
        retention_days=retention_days or 30,
        s3_config=s3_config,
    )
