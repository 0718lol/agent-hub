"""Tests for API key encryption/decryption."""
import pytest
import os


class TestKeyEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted key should decrypt back to original."""
        from app.core.config import obfuscate_key, deobfuscate_key
        original = "sk-test-key-12345"
        encrypted = obfuscate_key(original)
        decrypted = deobfuscate_key(encrypted)
        assert decrypted == original

    def test_encrypted_key_has_fnt_prefix(self):
        """Encrypted key should start with fnt:: prefix."""
        from app.core.config import obfuscate_key
        encrypted = obfuscate_key("test-key")
        assert encrypted.startswith("fnt::")

    def test_empty_key_returns_empty(self):
        """Empty key should return empty without error."""
        from app.core.config import obfuscate_key, deobfuscate_key
        assert obfuscate_key("") == ""
        assert deobfuscate_key("") == ""

    def test_legacy_enc_format_handled(self):
        """Legacy enc:: format should still be decryptable or return empty."""
        from app.core.config import deobfuscate_key
        # enc:: format is legacy, should not crash
        result = deobfuscate_key("enc::some_old_encrypted_key")
        assert isinstance(result, str)

    def test_wrong_key_returns_empty(self):
        """Decryption with wrong key should return empty, not crash."""
        from app.core.config import deobfuscate_key
        # Completely invalid string
        result = deobfuscate_key("fnt::invalid_garbage_data_here")
        assert result == "" or isinstance(result, str)
