"""Tests for session persistence."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from neow.core.session import SessionManager


class TestSessionManager:
    """Tests for SessionManager."""

    def test_init_creates_dir(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        manager = SessionManager(sessions_dir)
        assert sessions_dir.exists()

    def test_save_session(self, tmp_path):
        manager = SessionManager(tmp_path)
        mock_conv = MagicMock()
        mock_conv.messages = [{"role": "user", "content": "hello"}]
        mock_conv.context_files = {}
        mock_conv.system_prompt = "You are Neow."
        mock_conv.model_client = MagicMock()
        mock_conv.model_client.model = "deepseek-chat"

        name = manager.save(mock_conv, name="test-session")
        assert name == "test-session"

        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "test-session"

    def test_save_auto_name(self, tmp_path):
        manager = SessionManager(tmp_path)
        mock_conv = MagicMock()
        mock_conv.messages = []
        mock_conv.context_files = {}
        mock_conv.system_prompt = ""
        mock_conv.model_client = MagicMock()
        mock_conv.model_client.model = "deepseek-chat"

        name = manager.save(mock_conv)
        assert name is not None
        assert len(name) > 0

    def test_load_session(self, tmp_path):
        manager = SessionManager(tmp_path)
        mock_conv = MagicMock()
        mock_conv.messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        mock_conv.context_files = {"/tmp/test.py": "print('hi')"}
        mock_conv.system_prompt = "You are Neow."
        mock_conv.model_client = MagicMock()
        mock_conv.model_client.model = "deepseek-chat"

        manager.save(mock_conv, name="test-session")
        data = manager.load("test-session")

        assert data is not None
        assert data["name"] == "test-session"
        assert len(data["messages"]) == 2
        assert data["model"] == "deepseek-chat"

    def test_load_nonexistent(self, tmp_path):
        manager = SessionManager(tmp_path)
        data = manager.load("nonexistent")
        assert data is None

    def test_list_sessions_empty(self, tmp_path):
        manager = SessionManager(tmp_path)
        sessions = manager.list_sessions()
        assert sessions == []

    def test_list_sessions_sorted(self, tmp_path):
        manager = SessionManager(tmp_path)

        mock_conv = MagicMock()
        mock_conv.messages = []
        mock_conv.context_files = {}
        mock_conv.system_prompt = ""
        mock_conv.model_client = MagicMock()
        mock_conv.model_client.model = "deepseek-chat"

        manager.save(mock_conv, name="session-1")
        manager.save(mock_conv, name="session-2")

        sessions = manager.list_sessions()
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0]["created_at"] >= sessions[1]["created_at"]

    def test_restore_session(self, tmp_path):
        manager = SessionManager(tmp_path)
        mock_conv = MagicMock()
        mock_conv.messages = [{"role": "user", "content": "hello"}]
        mock_conv.context_files = {}
        mock_conv.system_prompt = "You are Neow."
        mock_conv.model_client = MagicMock()
        mock_conv.model_client.model = "deepseek-chat"

        manager.save(mock_conv, name="test-session")

        # Create a fresh conversation to restore into
        mock_new_conv = MagicMock()
        mock_new_conv.messages = []
        mock_new_conv.context_files = {}
        mock_new_conv.system_prompt = ""

        manager.restore("test-session", mock_new_conv)
        assert len(mock_new_conv.messages) == 1
        assert mock_new_conv.system_prompt == "You are Neow."
