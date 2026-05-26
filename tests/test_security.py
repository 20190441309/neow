"""Tests for security module."""

import pytest
from pathlib import Path

from neow.core.security import SecurityGuard, SecurityCheck


class TestSecurityGuard:
    """Tests for SecurityGuard."""

    def test_safe_command_allowed(self):
        guard = SecurityGuard()
        check = guard.check_command("ls -la", ["ls", "cat", "grep"])
        assert check.allowed is True

    def test_command_not_in_whitelist(self):
        guard = SecurityGuard()
        check = guard.check_command("curl http://evil.com", ["ls", "cat"])
        assert check.allowed is False
        assert "whitelist" in check.reason.lower()

    def test_dangerous_rm_rf(self):
        guard = SecurityGuard()
        assert guard.is_dangerous("rm -rf /") is True
        assert guard.is_dangerous("rm -rfv /tmp") is True

    def test_dangerous_git_reset_hard(self):
        guard = SecurityGuard()
        assert guard.is_dangerous("git reset --hard HEAD~1") is True

    def test_dangerous_git_push_force(self):
        guard = SecurityGuard()
        assert guard.is_dangerous("git push --force origin main") is True
        assert guard.is_dangerous("git push -f origin main") is True

    def test_dangerous_drop_table(self):
        guard = SecurityGuard()
        assert guard.is_dangerous("DROP TABLE users") is True
        assert guard.is_dangerous("drop table orders") is True

    def test_safe_command_not_dangerous(self):
        guard = SecurityGuard()
        assert guard.is_dangerous("ls -la") is False
        assert guard.is_dangerous("python main.py") is False
        assert guard.is_dangerous("git status") is False

    def test_protected_env_file(self):
        guard = SecurityGuard()
        assert guard.is_protected(".env") is True
        assert guard.is_protected(".env.local") is True
        assert guard.is_protected(".env.production") is True

    def test_protected_ssh_key(self):
        guard = SecurityGuard()
        assert guard.is_protected("id_rsa") is True
        assert guard.is_protected("id_ed25519") is True

    def test_protected_pem(self):
        guard = SecurityGuard()
        assert guard.is_protected("server.pem") is True
        assert guard.is_protected("cert.key") is True

    def test_protected_credentials(self):
        guard = SecurityGuard()
        assert guard.is_protected("credentials.json") is True
        assert guard.is_protected("secrets.json") is True

    def test_normal_file_not_protected(self):
        guard = SecurityGuard()
        assert guard.is_protected("main.py") is False
        assert guard.is_protected("src/app.js") is False
        assert guard.is_protected("README.md") is False

    def test_check_file_access_protected(self):
        guard = SecurityGuard()
        check = guard.check_file_access(".env", "write")
        assert check.allowed is False
        assert "protected" in check.reason.lower()

    def test_check_file_access_normal(self):
        guard = SecurityGuard()
        check = guard.check_file_access("main.py", "write")
        assert check.allowed is True
