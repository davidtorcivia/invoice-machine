"""Backup API endpoints."""

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import BusinessProfile, get_session
from invoicely.services import BackupService
from invoicely.crypto import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backups", tags=["backups"])
limiter = Limiter(key_func=get_remote_address)


class BackupSchema(BaseModel):
    """Backup file information."""
    filename: str
    size_bytes: int
    created_at: str
    compressed: bool = True
    location: str = "local"


class BackupResult(BaseModel):
    """Result of a backup operation."""
    filename: str
    path: str
    size_bytes: int
    timestamp: str
    compressed: bool
    uploaded_to_s3: bool
    s3_error: Optional[str] = None


class RestoreResult(BaseModel):
    """Result of a restore operation."""
    restored_from: str
    pre_restore_backup: Optional[str]
    timestamp: str
    message: str


class BackupSettingsSchema(BaseModel):
    """Backup settings."""
    backup_enabled: bool
    backup_retention_days: int
    backup_s3_enabled: bool
    backup_s3_endpoint_url: Optional[str] = None
    backup_s3_bucket: Optional[str] = None
    backup_s3_region: Optional[str] = None
    backup_s3_prefix: Optional[str] = None
    # Note: access keys are write-only, not returned in GET


class BackupSettingsUpdate(BaseModel):
    """Backup settings update."""
    backup_enabled: Optional[bool] = None
    backup_retention_days: Optional[int] = Field(None, ge=1, le=365)
    backup_s3_enabled: Optional[bool] = None
    backup_s3_endpoint_url: Optional[str] = Field(None, max_length=500)
    backup_s3_access_key_id: Optional[str] = Field(None, max_length=200)
    backup_s3_secret_access_key: Optional[str] = Field(None, max_length=200)
    backup_s3_bucket: Optional[str] = Field(None, max_length=200)
    backup_s3_region: Optional[str] = Field(None, max_length=50)
    backup_s3_prefix: Optional[str] = Field(None, max_length=200)


def _decrypt_s3_config(s3_config: dict) -> dict:
    """Decrypt S3 credentials in config dict."""
    if not s3_config:
        return s3_config

    result = s3_config.copy()

    # Decrypt access key ID
    if result.get("access_key_id"):
        try:
            result["access_key_id"] = decrypt_credential(result["access_key_id"])
        except ValueError:
            pass  # Keep original if decryption fails

    # Decrypt secret access key
    if result.get("secret_access_key"):
        try:
            result["secret_access_key"] = decrypt_credential(result["secret_access_key"])
        except ValueError:
            pass  # Keep original if decryption fails

    return result


async def get_backup_service(session: AsyncSession) -> BackupService:
    """Get backup service with settings from database."""
    profile = await BusinessProfile.get_or_create(session)

    s3_config = None
    if profile.backup_s3_enabled and profile.backup_s3_config:
        try:
            s3_config = json.loads(profile.backup_s3_config)
            s3_config = _decrypt_s3_config(s3_config)
            s3_config["enabled"] = True
        except json.JSONDecodeError:
            pass

    return BackupService(
        retention_days=profile.backup_retention_days or 30,
        s3_config=s3_config,
    )


@router.get("/settings", response_model=BackupSettingsSchema)
async def get_backup_settings(
    session: AsyncSession = Depends(get_session),
) -> BackupSettingsSchema:
    """Get current backup settings."""
    profile = await BusinessProfile.get_or_create(session)

    s3_config = {}
    if profile.backup_s3_config:
        try:
            s3_config = json.loads(profile.backup_s3_config)
        except json.JSONDecodeError:
            pass

    return BackupSettingsSchema(
        backup_enabled=bool(profile.backup_enabled),
        backup_retention_days=profile.backup_retention_days or 30,
        backup_s3_enabled=bool(profile.backup_s3_enabled),
        backup_s3_endpoint_url=s3_config.get("endpoint_url"),
        backup_s3_bucket=s3_config.get("bucket"),
        backup_s3_region=s3_config.get("region"),
        backup_s3_prefix=s3_config.get("prefix"),
    )


@router.put("/settings", response_model=BackupSettingsSchema)
async def update_backup_settings(
    updates: BackupSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> BackupSettingsSchema:
    """Update backup settings."""
    profile = await BusinessProfile.get_or_create(session)

    if updates.backup_enabled is not None:
        profile.backup_enabled = 1 if updates.backup_enabled else 0

    if updates.backup_retention_days is not None:
        profile.backup_retention_days = updates.backup_retention_days

    if updates.backup_s3_enabled is not None:
        profile.backup_s3_enabled = 1 if updates.backup_s3_enabled else 0

    # Handle S3 config updates
    s3_config = {}
    if profile.backup_s3_config:
        try:
            s3_config = json.loads(profile.backup_s3_config)
        except json.JSONDecodeError:
            pass

    if updates.backup_s3_endpoint_url is not None:
        s3_config["endpoint_url"] = updates.backup_s3_endpoint_url or None
    if updates.backup_s3_access_key_id is not None:
        # Encrypt access key ID before storage
        if updates.backup_s3_access_key_id:
            s3_config["access_key_id"] = encrypt_credential(updates.backup_s3_access_key_id)
        else:
            s3_config["access_key_id"] = None
    if updates.backup_s3_secret_access_key is not None:
        # Encrypt secret access key before storage
        if updates.backup_s3_secret_access_key:
            s3_config["secret_access_key"] = encrypt_credential(updates.backup_s3_secret_access_key)
        else:
            s3_config["secret_access_key"] = None
    if updates.backup_s3_bucket is not None:
        s3_config["bucket"] = updates.backup_s3_bucket or None
    if updates.backup_s3_region is not None:
        s3_config["region"] = updates.backup_s3_region or None
    if updates.backup_s3_prefix is not None:
        s3_config["prefix"] = updates.backup_s3_prefix or None

    profile.backup_s3_config = json.dumps(s3_config) if s3_config else None
    profile.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(profile)

    return BackupSettingsSchema(
        backup_enabled=bool(profile.backup_enabled),
        backup_retention_days=profile.backup_retention_days or 30,
        backup_s3_enabled=bool(profile.backup_s3_enabled),
        backup_s3_endpoint_url=s3_config.get("endpoint_url"),
        backup_s3_bucket=s3_config.get("bucket"),
        backup_s3_region=s3_config.get("region"),
        backup_s3_prefix=s3_config.get("prefix"),
    )


@router.get("", response_model=List[BackupSchema])
async def list_backups(
    include_s3: bool = Query(True, description="Include S3 backups"),
    session: AsyncSession = Depends(get_session),
) -> List[BackupSchema]:
    """List all available backups."""
    backup_service = await get_backup_service(session)

    # Get local backups
    backups = []
    for b in backup_service.list_backups():
        backups.append(BackupSchema(
            filename=b["filename"],
            size_bytes=b["size_bytes"],
            created_at=b["created_at"],
            compressed=b.get("compressed", True),
            location="local",
        ))

    # Get S3 backups if requested
    if include_s3:
        for b in backup_service.list_s3_backups():
            # Check if already in local list
            if not any(lb.filename == b["filename"] for lb in backups):
                backups.append(BackupSchema(
                    filename=b["filename"],
                    size_bytes=b["size_bytes"],
                    created_at=b["created_at"],
                    compressed=True,
                    location="s3",
                ))

    # Sort by date
    backups.sort(key=lambda x: x.created_at, reverse=True)
    return backups


@router.post("", response_model=BackupResult)
@limiter.limit("10/hour")
async def create_backup(
    request: Request,
    compress: bool = Query(True, description="Compress backup with gzip"),
    session: AsyncSession = Depends(get_session),
) -> BackupResult:
    """Create a new backup manually."""
    backup_service = await get_backup_service(session)

    try:
        result = backup_service.create_backup(compress=compress)
        return BackupResult(**result)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Database not found")
    except Exception as e:
        logger.error(f"Backup creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Backup failed. Check server logs for details.")


@router.post("/restore/{filename}", response_model=RestoreResult)
async def restore_backup(
    filename: str,
    download_from_s3: bool = Query(False, description="Download from S3 first"),
    session: AsyncSession = Depends(get_session),
) -> RestoreResult:
    """
    Restore database from a backup.

    Warning: This will overwrite the current database!
    A pre-restore backup is created automatically.
    The application should be restarted after restore.
    """
    backup_service = await get_backup_service(session)

    try:
        # Download from S3 if requested
        if download_from_s3:
            backup_service.download_from_s3(filename)

        result = backup_service.restore_backup(filename)
        return RestoreResult(**result)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup file not found")
    except ValueError as e:
        # ValueError contains user-facing validation messages (e.g., path traversal)
        error_msg = str(e)
        # Only expose safe validation messages
        if "Invalid backup filename" in error_msg or "Invalid SQLite database" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail="Invalid backup file")
    except Exception as e:
        logger.error(f"Restore failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Restore failed. Check server logs for details.")


@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    session: AsyncSession = Depends(get_session),
):
    """Download a backup file."""
    backup_service = await get_backup_service(session)

    backup_path = backup_service.backup_dir / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    # Security: ensure path is within backup directory
    if not str(backup_path.resolve()).startswith(str(backup_service.backup_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid backup path")

    return FileResponse(
        backup_path,
        media_type="application/octet-stream",
        filename=filename,
    )


@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a backup file."""
    backup_service = await get_backup_service(session)

    if not backup_service.delete_backup(filename):
        raise HTTPException(status_code=404, detail="Backup not found")

    return {"success": True, "deleted": filename}


@router.post("/cleanup")
async def cleanup_old_backups(
    session: AsyncSession = Depends(get_session),
):
    """Delete backups older than retention period."""
    backup_service = await get_backup_service(session)

    deleted = backup_service.cleanup_old_backups()
    return {"success": True, "deleted_count": deleted}


@router.post("/test-s3")
@limiter.limit("10/minute")
async def test_s3_connection(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Test S3 connection with current settings."""
    profile = await BusinessProfile.get_or_create(session)

    if not profile.backup_s3_enabled or not profile.backup_s3_config:
        raise HTTPException(status_code=400, detail="S3 is not configured")

    try:
        s3_config = json.loads(profile.backup_s3_config)
        # Decrypt credentials for use
        s3_config = _decrypt_s3_config(s3_config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid S3 configuration")

    try:
        import boto3
        from botocore.config import Config

        s3_client = boto3.client(
            "s3",
            endpoint_url=s3_config.get("endpoint_url"),
            aws_access_key_id=s3_config.get("access_key_id"),
            aws_secret_access_key=s3_config.get("secret_access_key"),
            region_name=s3_config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        # Test by listing bucket (will fail if credentials are wrong)
        bucket = s3_config.get("bucket")
        s3_client.head_bucket(Bucket=bucket)

        return {"success": True, "message": f"Successfully connected to bucket: {bucket}"}
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="boto3 is not installed. Run: pip install boto3"
        )
    except Exception as e:
        logger.error(f"S3 connection failed: {e}", exc_info=True)
        # Don't expose detailed S3 error messages which may contain bucket names, regions, etc.
        raise HTTPException(status_code=400, detail="S3 connection failed. Check your credentials and configuration.")
