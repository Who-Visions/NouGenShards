import os
import pytest
from pathlib import Path
from nougen_shards import tunnel

def test_get_ngrok_token_from_env(monkeypatch):
    monkeypatch.setenv("NGROK_AUTHTOKEN", "test_env_token_12345")
    token = tunnel.get_ngrok_token()
    assert token == "test_env_token_12345"

def test_get_ngrok_token_from_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)
    vault_file = tmp_path / "ngrok.env"
    vault_file.write_text('NGROK_AUTHTOKEN="vault_token_abcde"\n')
    monkeypatch.setattr(tunnel, "VAULT_PATH", vault_file)
    
    token = tunnel.get_ngrok_token()
    assert token == "vault_token_abcde"

def test_get_ngrok_token_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)
    non_existent = tmp_path / "non_existent.env"
    monkeypatch.setattr(tunnel, "VAULT_PATH", non_existent)
    
    token = tunnel.get_ngrok_token()
    assert token == ""
