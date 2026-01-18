"""Cryptographic utilities for credential encryption and API key hashing."""

import base64
import hashlib
import os
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


def _get_encryption_key() -> bytes:
    """
    Get or generate encryption key from environment.

    Key is stored in INVOICELY_ENCRYPTION_KEY environment variable.
    If not set, generates a key and logs a warning.
    """
    key = os.environ.get("INVOICELY_ENCRYPTION_KEY")

    if key:
        # Validate key format (must be 32 bytes, base64-encoded = 44 chars)
        try:
            decoded = base64.urlsafe_b64decode(key.encode())
            if len(decoded) == 32:
                return key.encode()
        except Exception:
            pass

    # No valid key found - use a derived key from a secret
    # This is a fallback for development; production should set the env var
    import logging
    logging.warning(
        "INVOICELY_ENCRYPTION_KEY not set. Using derived key. "
        "For production, set INVOICELY_ENCRYPTION_KEY to a 32-byte base64-encoded value."
    )

    # Derive from a machine-specific value to maintain consistency
    # In production this should be a proper secret
    machine_id = os.environ.get("HOSTNAME", "invoicely-default")
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        machine_id.encode(),
        b"invoicely-salt-v1",
        100000
    )
    return base64.urlsafe_b64encode(derived)


def generate_encryption_key() -> str:
    """
    Generate a new encryption key for use in INVOICELY_ENCRYPTION_KEY.

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


def decrypt_credential(ciphertext: str) -> str:
    """
    Decrypt an encrypted credential.

    Args:
        ciphertext: The encrypted credential (with 'enc:' prefix)

    Returns:
        Decrypted plaintext string

    Raises:
        ValueError: If decryption fails
    """
    if not ciphertext:
        return ciphertext

    # Check if this is an encrypted value
    if not ciphertext.startswith("enc:"):
        # Return as-is for backwards compatibility with unencrypted values
        return ciphertext

    try:
        key = _get_encryption_key()
        f = Fernet(key)
        encrypted_data = ciphertext[4:].encode()  # Remove 'enc:' prefix
        decrypted = f.decrypt(encrypted_data)
        return decrypted.decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt credential. Encryption key may have changed.")


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

    Args:
        api_key: The plain API key to verify
        hashed: The stored hash in format 'hash:<salt>:<hash>'

    Returns:
        True if the key matches, False otherwise
    """
    if not hashed or not api_key:
        return False

    # Handle legacy unhashed keys for backwards compatibility
    if not hashed.startswith("hash:"):
        # Legacy plain-text comparison (will be migrated on next key generation)
        return secrets.compare_digest(api_key, hashed)

    try:
        _, salt, stored_hash = hashed.split(":", 2)
        computed_hash = hashlib.sha256((salt + api_key).encode()).hexdigest()
        return secrets.compare_digest(computed_hash, stored_hash)
    except ValueError:
        return False


def generate_api_key() -> str:
    """Generate a new random API key."""
    return secrets.token_hex(32)  # 64 character hex string
