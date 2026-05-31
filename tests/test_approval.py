"""Tests for approval mode."""

import pytest

from neow.core.approval import (
    ApprovalMode,
    ApprovalTier,
    ApprovalCheck,
    ApprovalPolicy,
    TOOL_TIERS,
)
from neow.core.executor import ToolExecutor, ToolError
from neow.core.security import SecurityGuard


class TestApprovalMode:
    """Tests for ApprovalMode enum."""

    def test_mode_values(self):
        assert ApprovalMode.ALWAYS_ASK.value == "always-ask"
        assert ApprovalMode.WRITE.value == "write"
        assert ApprovalMode.YOLO.value == "yolo"

    def test_mode_from_string(self):
        assert ApprovalMode("always-ask") == ApprovalMode.ALWAYS_ASK
        assert ApprovalMode("write") == ApprovalMode.WRITE
        assert ApprovalMode("yolo") == ApprovalMode.YOLO

    def test_invalid_mode_string(self):
        with pytest.raises(ValueError):
            ApprovalMode("invalid")


class TestApprovalTier:
    """Tests for ApprovalTier enum."""

    def test_tier_values(self):
        assert ApprovalTier.READ.value == "read"
        assert ApprovalTier.WRITE.value == "write"
        assert ApprovalTier.EXEC.value == "exec"

    def test_tool_tiers_mapping(self):
        assert TOOL_TIERS["read_file"] == ApprovalTier.READ
        assert TOOL_TIERS["search_code"] == ApprovalTier.READ
        assert TOOL_TIERS["write_file"] == ApprovalTier.WRITE
        assert TOOL_TIERS["edit_file"] == ApprovalTier.WRITE
        assert TOOL_TIERS["create_file"] == ApprovalTier.WRITE
        assert TOOL_TIERS["delete_file"] == ApprovalTier.WRITE
        assert TOOL_TIERS["execute_command"] == ApprovalTier.EXEC


class TestApprovalCheck:
    """Tests for ApprovalCheck."""

    def test_needs_approval_true(self):
        check = ApprovalCheck(needs_approval=True, reason="test", tool_name="edit_file")
        assert bool(check) is True
        assert check.needs_approval is True
        assert check.tool_name == "edit_file"

    def test_needs_approval_false(self):
        check = ApprovalCheck(needs_approval=False, reason="", tool_name="read_file")
        assert bool(check) is False
        assert check.needs_approval is False

    def test_repr(self):
        check = ApprovalCheck(needs_approval=True, reason="test", tool_name="edit_file")
        assert "edit_file" in repr(check)


class TestApprovalPolicy:
    """Tests for ApprovalPolicy."""

    def test_yolo_mode_allows_everything(self):
        policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
        for tool_name in TOOL_TIERS:
            check = policy.check_approval(tool_name)
            assert check.needs_approval is False, f"YOLO should allow {tool_name}"

    def test_yolo_mode_blocks_dangerous(self):
        policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
        check = policy.check_approval("execute_command", is_dangerous=True)
        assert check.needs_approval is True

    def test_write_mode_allows_reads(self):
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        assert policy.check_approval("read_file").needs_approval is False
        assert policy.check_approval("search_code").needs_approval is False
        assert policy.check_approval("git_status").needs_approval is False
        assert policy.check_approval("git_diff").needs_approval is False

    def test_write_mode_blocks_writes(self):
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        assert policy.check_approval("write_file").needs_approval is True
        assert policy.check_approval("edit_file").needs_approval is True
        assert policy.check_approval("create_file").needs_approval is True
        assert policy.check_approval("delete_file").needs_approval is True

    def test_write_mode_blocks_exec(self):
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        assert policy.check_approval("execute_command").needs_approval is True

    def test_always_ask_blocks_everything(self):
        policy = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
        for tool_name in TOOL_TIERS:
            check = policy.check_approval(tool_name)
            assert check.needs_approval is True, f"always-ask should block {tool_name}"

    def test_always_ask_blocks_dangerous(self):
        policy = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
        check = policy.check_approval("execute_command", is_dangerous=True)
        assert check.needs_approval is True

    def test_tool_override_allow(self):
        policy = ApprovalPolicy(
            mode=ApprovalMode.ALWAYS_ASK,
            tool_overrides={"write_file": "allow"},
        )
        check = policy.check_approval("write_file")
        assert check.needs_approval is False

    def test_tool_override_deny(self):
        policy = ApprovalPolicy(
            mode=ApprovalMode.YOLO,
            tool_overrides={"read_file": "deny"},
        )
        check = policy.check_approval("read_file")
        assert check.needs_approval is True

    def test_tool_override_prompt(self):
        policy = ApprovalPolicy(
            mode=ApprovalMode.YOLO,
            tool_overrides={"read_file": "prompt"},
        )
        check = policy.check_approval("read_file")
        assert check.needs_approval is True

    def test_override_takes_precedence_over_mode(self):
        """Even in YOLO mode, a 'prompt' override forces approval."""
        policy = ApprovalPolicy(
            mode=ApprovalMode.YOLO,
            tool_overrides={"execute_command": "prompt"},
        )
        check = policy.check_approval("execute_command")
        assert check.needs_approval is True

    def test_dangerous_always_overrides(self):
        """Even with 'allow' override, dangerous operations still need approval."""
        policy = ApprovalPolicy(
            mode=ApprovalMode.YOLO,
            tool_overrides={"execute_command": "allow"},
        )
        check = policy.check_approval("execute_command", is_dangerous=True)
        assert check.needs_approval is True

    def test_unknown_tool_gets_exec_tier(self):
        """Unknown tools default to EXEC tier."""
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        check = policy.check_approval("unknown_tool")
        assert check.needs_approval is True
        assert check.tier == ApprovalTier.EXEC

    def test_set_mode(self):
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        policy.set_mode(ApprovalMode.YOLO)
        assert policy.mode == ApprovalMode.YOLO
        # Now write_file should be allowed
        assert policy.check_approval("write_file").needs_approval is False

    def test_set_tool_override(self):
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        policy.set_tool_override("execute_command", "allow")
        assert policy.tool_overrides["execute_command"] == "allow"
        assert policy.check_approval("execute_command").needs_approval is False

    def test_set_tool_override_invalid(self):
        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        with pytest.raises(ValueError, match="Invalid override policy"):
            policy.set_tool_override("execute_command", "maybe")

    def test_default_mode_is_write(self):
        policy = ApprovalPolicy()
        assert policy.mode == ApprovalMode.WRITE


class TestExecutorApprovalGate:
    """Tests for approval gate in ToolExecutor."""

    def test_yolo_mode_executes_directly(self, tmp_path):
        """YOLO mode should execute tools without approval callback."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()
        test_file = tmp_path / "test.txt"

        # Register real write_file
        from neow.tools.file_ops import write_file
        executor.register_tool("write_file", write_file)

        policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
        executor.approval_policy = policy
        # No approval_callback set

        # Should succeed without callback in YOLO mode
        result = executor.execute("write_file", {"file_path": str(test_file), "content": "hello"})
        assert "successfully" in result.lower()
        assert test_file.read_text() == "hello"

    def test_write_mode_denies_without_callback(self):
        """Write mode should deny execution if no approval callback is set."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()

        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        executor.approval_policy = policy
        # No approval_callback set

        with pytest.raises(ToolError, match="Approval required"):
            executor.execute("write_file", {"file_path": "/tmp/test.txt", "content": "hello"})

    def test_approval_callback_approved(self, tmp_path):
        """Approved tool should execute when callback returns True."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()
        from neow.tools.file_ops import write_file
        executor.register_tool("write_file", write_file)

        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        executor.approval_policy = policy
        executor.approval_callback = lambda name, params, reason: True

        test_file = tmp_path / "test.txt"
        result = executor.execute("write_file", {"file_path": str(test_file), "content": "hello"})
        assert test_file.read_text() == "hello"

    def test_approval_callback_denied(self):
        """Denied tool should raise ToolError when callback returns False."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()

        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        executor.approval_policy = policy
        executor.approval_callback = lambda name, params, reason: False

        with pytest.raises(ToolError, match="User denied"):
            executor.execute("write_file", {"file_path": "/tmp/test.txt", "content": "hello"})

    def test_read_tools_bypass_approval_in_write_mode(self, tmp_path):
        """Read operations should not need approval in write mode."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()
        from neow.tools.file_ops import read_file, write_file
        executor.register_tool("read_file", read_file)
        executor.register_tool("write_file", write_file)

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        executor.approval_policy = policy
        # No callback -- reads should still work

        result = executor.execute("read_file", {"file_path": str(test_file)})
        # read_file now appends ¶PATH#HASH annotation
        assert result.startswith("hello")
        assert "¶" in result

    def test_dangerous_command_forces_approval(self):
        """Dangerous commands should force approval even in YOLO mode."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()
        executor.security_guard = SecurityGuard()

        policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
        executor.approval_policy = policy
        # No callback -- dangerous should still fail

        with pytest.raises(ToolError, match="Approval required|Security"):
            executor.execute("execute_command", {"command": "rm -rf /"})

    def test_callback_receives_reason(self):
        """Approval callback should receive the reason string."""
        from neow.core.approval import ApprovalPolicy
        executor = ToolExecutor()

        captured_reason = []
        def capture_callback(name, params, reason):
            captured_reason.append(reason)
            return True

        policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
        executor.approval_policy = policy
        executor.approval_callback = capture_callback

        # This will fail because write_file stub raises NotImplementedError,
        # but the callback should have been called first
        try:
            executor.execute("write_file", {"file_path": "/tmp/test.txt", "content": "hello"})
        except ToolError:
            pass  # Expected -- stub raises

        assert len(captured_reason) == 1
        assert "write" in captured_reason[0].lower() or "approval" in captured_reason[0].lower()
