"""Fernet encryption for OAuth tokens at rest.

Tokens are encrypted before storage in the ``google_drive_connections`` table
and decrypted only when needed for API calls.  The encryption key comes from
the ``GDRIVE_ENCRYPTION_KEY`` environment variable (a URL-safe base64 Fernet key).
"""

from __future__ import annotations

from cryptography.fernet import Fernet


def generate_key() -> str:
    """Generate a new Fernet encryption key (for bootstrapping ``.env``)."""
    return Fernet.generate_key().decode()


def encrypt_tokens(plaintext: str, key: str) -> str:
    """Encrypt a JSON string of tokens and return the ciphertext as a string."""
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_tokens(ciphertext: str, key: str) -> str:
    """Decrypt ciphertext back to the original JSON string.

    Raises ``cryptography.fernet.InvalidToken`` if the key is wrong or data is
    corrupted — callers should handle this as a connection-revoked scenario.
    """
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()
