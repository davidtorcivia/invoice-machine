"""Cryptographic utilities for credential encryption and API key hashing.

Security notes:
- Encryption key MUST be set via INVOICE_MACHINE_ENCRYPTION_KEY in production
- Plaintext credential storage is NOT supported (migration required)
- API keys are hashed with per-key salt using SHA-256
"""

import base64
import hashlib
import logging
import os
import re
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

# Cache the encryption key after first retrieval
_cached_key: Optional[bytes] = None


class EncryptionKeyError(Exception):
    """Raised when encryption key is missing or invalid."""

    pass


def _get_encryption_key() -> bytes:
    """
    Get encryption key from environment variable.

    SECURITY: In production, this function will FAIL if the key is not set.
    Development mode allows a derived key with a warning.

    Returns:
        The encryption key as bytes

    Raises:
        EncryptionKeyError: If key is missing in production or invalid format
    """
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    key = os.environ.get("INVOICE_MACHINE_ENCRYPTION_KEY")
    environment = os.environ.get("ENVIRONMENT", "development").lower()

    if key:
        key = key.strip()

        # Accept 64-char hex keys for backwards compatibility
        if re.fullmatch(r"[0-9a-fA-F]{64}", key):
            decoded = bytes.fromhex(key)
            _cached_key = base64.urlsafe_b64encode(decoded)
            return _cached_key

        # Validate base64 format (must decode to 32 bytes)
        try:
            decoded = base64.urlsafe_b64decode(key.encode())
            if len(decoded) == 32:
                _cached_key = key.encode()
                return _cached_key
            else:
                raise EncryptionKeyError(
                    "INVOICE_MACHINE_ENCRYPTION_KEY must be a 32-byte base64 value or 64 hex characters. "
                    f"Got {len(decoded)} bytes. Generate a new key with: "
                    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
        except (ValueError, TypeError) as e:
            raise EncryptionKeyError(
                f"INVOICE_MACHINE_ENCRYPTION_KEY has invalid format: {e}. "
                "Generate a new key with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

    # No key found - behavior depends on environment
    if environment == "production":
        raise EncryptionKeyError(
            "INVOICE_MACHINE_ENCRYPTION_KEY environment variable is REQUIRED in production. "
            "Generate a key with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # Development mode: generate a deterministic key with warning
    logging.warning(
        "INVOICE_MACHINE_ENCRYPTION_KEY not set. Using derived key for DEVELOPMENT ONLY. "
        "For production, set INVOICE_MACHINE_ENCRYPTION_KEY to a 32-byte base64-encoded value."
    )

    # Derive from a machine-specific value to maintain consistency in development
    machine_id = os.environ.get("HOSTNAME", "invoice-machine-dev-default")
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        machine_id.encode(),
        b"invoice-machine-dev-salt-v1",
        600000,  # OWASP recommended minimum for PBKDF2-HMAC-SHA256
    )
    _cached_key = base64.urlsafe_b64encode(derived)
    return _cached_key


def generate_encryption_key() -> str:
    """
    Generate a new encryption key for use in INVOICE_MACHINE_ENCRYPTION_KEY.

    Returns a base64-encoded 32-byte key suitable for Fernet encryption.
    """
    return Fernet.generate_key().decode()


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential (password, API key, etc.) for storage.

    Args:
        plaintext: The credential to encrypt

    Returns:
        Base64-encoded encrypted string with 'enc:' prefix
    """
    if not plaintext:
        return plaintext

    key = _get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(plaintext.encode())
    return f"enc:{encrypted.decode()}"


class UnencryptedCredentialError(Exception):
    """Raised when an unencrypted credential is encountered."""

    pass


def decrypt_credential(ciphertext: str, allow_plaintext: bool = False) -> str:
    """
    Decrypt an encrypted credential.

    SECURITY: Plaintext credentials are NOT allowed by default. This prevents
    downgrade attacks where an attacker replaces encrypted data with plaintext.

    Args:
        ciphertext: The encrypted credential (with 'enc:' prefix)
        allow_plaintext: If True, allows returning plaintext values (DEVELOPMENT ONLY)

    Returns:
        Decrypted plaintext string

    Raises:
        ValueError: If decryption fails
        UnencryptedCredentialError: If credential is not encrypted and allow_plaintext=False
    """
    if not ciphertext:
        return ciphertext

    # Check if this is an encrypted value
    if not ciphertext.startswith("enc:"):
        environment = os.environ.get("ENVIRONMENT", "development").lower()

        # SECURITY: Never allow plaintext in production
        if environment == "production":
            raise UnencryptedCredentialError(
                "Unencrypted credential detected in production. "
                "All credentials must be encrypted. Please re-save the credential to encrypt it."
            )

        if not allow_plaintext:
            logging.warning(
                "Unencrypted credential detected. Please re-save to encrypt. "
                "Plaintext credentials will be rejected in production."
            )

        # Development only: return plaintext with warning
        return ciphertext

    try:
        key = _get_encryption_key()
        f = Fernet(key)
        encrypted_data = ciphertext[4:].encode()  # Remove 'enc:' prefix
        decrypted = f.decrypt(encrypted_data)
        return decrypted.decode()
    except InvalidToken:
        raise ValueError(
            "Failed to decrypt credential. The encryption key may have changed. "
            "If you changed the encryption key, you'll need to re-enter any saved credentials."
        )


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted (has 'enc:' prefix)."""
    return value and value.startswith("enc:")


# MCP API Key hashing

def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.

    Uses SHA-256 with a unique salt for each key.

    Args:
        api_key: The plain API key

    Returns:
        Hashed key in format 'hash:<salt>:<hash>'
    """
    salt = secrets.token_hex(16)
    hash_value = hashlib.sha256((salt + api_key).encode()).hexdigest()
    return f"hash:{salt}:{hash_value}"


def verify_api_key(api_key: str, hashed: str) -> bool:
    """
    Verify an API key against its hash.

    SECURITY: Plaintext API keys are logged as warnings but still accepted
    for backwards compatibility. They should be regenerated.

    Args:
        api_key: The plain API key to verify
        hashed: The stored hash in format 'hash:<salt>:<hash>'

    Returns:
        True if the key matches, False otherwise
    """
    if not hashed or not api_key:
        return False

    # Check for legacy unhashed keys
    if not hashed.startswith("hash:"):
        environment = os.environ.get("ENVIRONMENT", "development").lower()

        if environment == "production":
            logging.error(
                "SECURITY WARNING: Unhashed API key detected in production. "
                "Please regenerate the API key to ensure it is properly hashed."
            )

        # Still allow comparison but log warning
        logging.warning(
            "Unhashed API key detected. Please regenerate the API key "
            "via the MCP settings page for improved security."
        )
        return secrets.compare_digest(api_key, hashed)

    try:
        _, salt, stored_hash = hashed.split(":", 2)
        computed_hash = hashlib.sha256((salt + api_key).encode()).hexdigest()
        return secrets.compare_digest(computed_hash, stored_hash)
    except ValueError:
        return False


def needs_credential_migration(value: str) -> bool:
    """Check if a credential needs to be migrated (encrypted).

    Args:
        value: The stored credential value

    Returns:
        True if the credential is plaintext and needs encryption
    """
    if not value:
        return False
    return not value.startswith("enc:")


def needs_api_key_migration(hashed: str) -> bool:
    """Check if an API key needs to be migrated (hashed).

    Args:
        hashed: The stored API key value

    Returns:
        True if the API key is plaintext and needs hashing
    """
    if not hashed:
        return False
    return not hashed.startswith("hash:")


def generate_api_key() -> str:
    """Generate a new random API key."""
    return secrets.token_hex(32)  # 64 character hex string
