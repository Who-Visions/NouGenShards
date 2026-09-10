import os
import unittest
from unittest.mock import MagicMock, patch

from nougen_shards.models_client import OllamaClient, OllamaCloudClient, WhoVisionsCloudClient
from nougen_shards.vram_gate import check_vram


class TestOllamaCloudClient(unittest.TestCase):
    def test_vram_gate_admits_cloud_model(self):
        with patch.dict(os.environ, {'NOUGEN_VRAM_GATE': '1'}):
            v = check_vram('gemma4:cloud')
            self.assertTrue(v.ok)
            self.assertIn('Ollama Cloud gateway', v.reason)

    def test_ollama_cloud_client_alias(self):
        self.assertIs(WhoVisionsCloudClient, OllamaCloudClient)

    def test_ollama_cloud_client_list_models(self):
        client = OllamaCloudClient()
        models = client.list_models()
        self.assertIn('gemma4:cloud', models)
        self.assertIn('qwen3.5:cloud', models)

    @patch('ollama.chat')
    def test_ollama_cloud_client_chat(self, mock_chat):
        mock_resp = MagicMock()
        mock_resp.message.content = 'Hello from gemma4:cloud!'
        mock_resp.message.thinking = None
        mock_chat.return_value = mock_resp

        client = OllamaCloudClient(default_model='gemma4:cloud')
        content = client.chat(messages=[{'role': 'user', 'content': 'Hello!'}])
        self.assertEqual(content, 'Hello from gemma4:cloud!')
        mock_chat.assert_called_once_with(
            model='gemma4:cloud',
            messages=[{'role': 'user', 'content': 'Hello!'}],
            stream=False,
        )

    @patch('ollama.chat')
    def test_ollama_client_chat_delegates_cloud_model(self, mock_chat):
        mock_resp = MagicMock()
        mock_resp.message.content = 'Direct cloud response'
        mock_resp.message.thinking = None
        mock_chat.return_value = mock_resp

        client = OllamaClient()
        content = client.chat('gemma4:cloud', [{'role': 'user', 'content': 'Ping'}])
        self.assertEqual(content, 'Direct cloud response')
        mock_chat.assert_called_once_with(
            model='gemma4:cloud',
            messages=[{'role': 'user', 'content': 'Ping'}],
            stream=False,
        )
