"""Шифрование идентификаторов админов для хранения в базе.

Потоковый шифр на SHA-256: гамма строится от токена бота и случайной соли,
целостность закрывает HMAC-SHA256. Только стандартная библиотека.
"""
import base64
import hashlib
import hmac
import os

import config

salt_size = 16
tag_size = 32
block_size = 32


def _derive_key(salt: bytes, purpose: bytes) -> bytes:
    return hashlib.sha256(config.bot_token.encode() + purpose + salt).digest()


def _keystream(key: bytes, length: int) -> bytes:
    blocks_needed = (length + block_size - 1) // block_size
    blocks = b"".join(hashlib.sha256(key + index.to_bytes(8, "big")).digest() for index in range(blocks_needed))
    return blocks[:length]


def _xor(raw: bytes, stream: bytes) -> bytes:
    return bytes(value ^ mask for value, mask in zip(raw, stream))


def encrypt_identifier(identifier: int) -> str:
    raw = str(identifier).encode()
    salt = os.urandom(salt_size)
    cipher = _xor(raw, _keystream(_derive_key(salt, b"enc"), len(raw)))
    tag = hmac.new(_derive_key(salt, b"mac"), cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(salt + cipher + tag).decode()


def decrypt_identifier(blob: str) -> int:
    data = base64.urlsafe_b64decode(blob.encode())
    if len(data) < salt_size + tag_size:
        raise ValueError("повреждённая запись")
    salt, cipher, tag = data[:salt_size], data[salt_size:-tag_size], data[-tag_size:]
    expected = hmac.new(_derive_key(salt, b"mac"), cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("подпись не совпала")
    return int(_xor(cipher, _keystream(_derive_key(salt, b"enc"), len(cipher))))
