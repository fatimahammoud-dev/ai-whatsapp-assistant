"""Encrypted storage for third-party credentials.

The tokens the platform holds — WhatsApp access tokens, calendar OAuth
tokens — let anyone who has them act as the tenant. Storing them as plain
bytes means a database dump, a replica, or a backup hands them over intact.

EncryptedBinaryField encrypts on the way in and decrypts on the way out, so
the column holds ciphertext and Python code keeps working with bytes.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.functional import cached_property


class EncryptedBinaryField(models.BinaryField):
    """A BinaryField whose value is Fernet-encrypted at rest."""

    @cached_property
    def fernet(self):
        from cryptography.fernet import Fernet

        key = getattr(settings, "TOKEN_ENCRYPTION_KEY", None)
        if not key:
            raise ImproperlyConfigured(
                "TOKEN_ENCRYPTION_KEY must be set to read or write encrypted "
                "fields. Generate one with: python -c 'from cryptography."
                "fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        return Fernet(key)

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.encode()
        elif isinstance(value, memoryview):
            value = bytes(value)
        return super().get_prep_value(self.fernet.encrypt(value))

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        from cryptography.fernet import InvalidToken

        try:
            return self.fernet.decrypt(bytes(value))
        except InvalidToken as exc:
            raise ValueError(
                f"{self.model.__name__}.{self.name} could not be decrypted. "
                "TOKEN_ENCRYPTION_KEY has probably changed since it was written."
            ) from exc
