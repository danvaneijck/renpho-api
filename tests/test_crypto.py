"""Tests for renpho.crypto — AES encrypt/decrypt round-trips."""

import json

from renpho.crypto import (
    aes_decrypt,
    aes_encrypt,
    decrypt_response,
    encrypt_empty_bytes,
    encrypt_empty_object,
    encrypt_request,
)

# Produced independently with OpenSSL, so a change in the crypto library that
# still round-trips but no longer matches what Renpho's server expects fails:
#   printf '%s' '{"pageNum":1,"pageSize":50}' \
#     | openssl enc -aes-128-ecb -K "$(printf '%s' 'ed*wijdi$h6fe3ew' | xxd -p)" -nosalt \
#     | base64
KNOWN_PLAINTEXT = '{"pageNum":1,"pageSize":50}'
KNOWN_CIPHERTEXT = "TQpN5l9b9crECU9E+tI7XgT/83F2rAmduNI+2X4IH5M="


def test_aes_matches_openssl_known_answer():
    assert aes_encrypt(KNOWN_PLAINTEXT) == KNOWN_CIPHERTEXT
    assert aes_decrypt(KNOWN_CIPHERTEXT) == KNOWN_PLAINTEXT


def test_aes_round_trip():
    plaintext = "hello world"
    encrypted = aes_encrypt(plaintext)
    assert aes_decrypt(encrypted) == plaintext


def test_aes_round_trip_json():
    payload = {"email": "test@example.com", "count": 42}
    serialized = json.dumps(payload, separators=(",", ":"))
    encrypted = aes_encrypt(serialized)
    decrypted = aes_decrypt(encrypted)
    assert json.loads(decrypted) == payload


def test_encrypt_request_format():
    result = encrypt_request({"key": "value"})
    assert "encryptData" in result
    assert isinstance(result["encryptData"], str)
    # Decrypt and verify
    decrypted = decrypt_response(result["encryptData"])
    assert decrypted == {"key": "value"}


def test_encrypt_empty_object():
    result = encrypt_empty_object()
    assert "encryptData" in result
    decrypted = decrypt_response(result["encryptData"])
    assert decrypted == {}


def test_encrypt_empty_bytes():
    result = encrypt_empty_bytes()
    assert "encryptData" in result
    assert isinstance(result["encryptData"], str)


def test_custom_key():
    key = "0123456789abcdef"  # 16 bytes
    encrypted = aes_encrypt("test", key=key)
    assert aes_decrypt(encrypted, key=key) == "test"
