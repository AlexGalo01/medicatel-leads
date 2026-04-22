from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from mle.services.jwt_service import create_access_token, decode_access_token
from mle.services.passwords import hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self) -> None:
        h = hash_password("correct-horse-battery")
        self.assertTrue(verify_password("correct-horse-battery", h))
        self.assertFalse(verify_password("wrong", h))


class JwtTests(unittest.TestCase):
    @patch("mle.services.jwt_service.get_settings")
    def test_encode_decode_roundtrip(self, mock_settings) -> None:
        m = mock_settings.return_value
        m.jwt_secret = "test-secret-key"
        m.jwt_algorithm = "HS256"
        m.jwt_expires_hours = 24
        uid = uuid4()
        token = create_access_token(user_id=uid)
        out = decode_access_token(token)
        self.assertEqual(out, uid)


if __name__ == "__main__":
    unittest.main()
