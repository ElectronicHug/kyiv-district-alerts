import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import yaml
from src.telegram.listener import check_config, list_groups

ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def test_placeholder_destination_is_rejected_offline(self):
        with self.assertRaisesRegex(ValueError, '--list-groups'):
            check_config(ROOT / 'config.example.yaml')

    def test_personalized_sample_validates_without_credentials_or_network(self):
        data = yaml.safe_load((ROOT / 'config.example.yaml').read_text(encoding='utf-8'))
        data['telegram']['output_peer_id'] = -123456789
        data['telegram']['output_name'] = 'Demo group'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
            with patch('src.telegram.listener.TelegramClient') as client:
                check_config(path)
                client.assert_not_called()

    def test_group_listing_only_prints_groups_and_sends_nothing(self):
        class Dialog:
            def __init__(self, group, name, entity):
                self.is_group, self.name, self.entity = group, name, entity

        async def dialogs():
            for dialog in (Dialog(False, 'Private contact', 1), Dialog(True, 'Demo group', 2)):
                yield dialog

        client = AsyncMock()
        client.__aenter__.return_value = client
        client.iter_dialogs = dialogs
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch('src.telegram.listener.PROJECT_ROOT', Path(directory)), \
                 patch('src.telegram.listener.load_credentials', return_value=(12345, '0' * 32)), \
                 patch('src.telegram.listener.load_telegram_ipv6', return_value=False), \
                 patch('src.telegram.listener.TelegramClient', return_value=client), \
                 patch('src.telegram.listener.utils.get_peer_id', return_value=-123456789), \
                 redirect_stdout(output):
                asyncio.run(list_groups())
            self.assertIn('-123456789\tDemo group', output.getvalue())
            self.assertNotIn('Private contact', output.getvalue())
            client.send_message.assert_not_called()


if __name__ == '__main__':
    unittest.main()
