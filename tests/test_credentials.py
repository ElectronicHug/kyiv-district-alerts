import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.credentials import load_credentials, load_telegram_ipv6


class CredentialTests(unittest.TestCase):
    def test_utf8_env_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "# local credentials\nTELEGRAM_API_ID=12345\nTELEGRAM_API_HASH=0123456789abcdef0123456789abcdef\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(load_credentials(root)[0], 12345)
            with patch.dict("os.environ", {"TELEGRAM_API_ID": "67890"}, clear=True):
                self.assertEqual(load_credentials(root)[0], 67890)

    def test_ipv6_option_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {}, clear=True):
                self.assertFalse(load_telegram_ipv6(root))
            with patch.dict("os.environ", {"TELEGRAM_USE_IPV6": "1"}, clear=True):
                self.assertTrue(load_telegram_ipv6(root))
            with patch.dict("os.environ", {"TELEGRAM_USE_IPV6": "yes"}, clear=True):
                with self.assertRaises(ValueError):
                    load_telegram_ipv6(root)


if __name__ == "__main__":
    unittest.main()
