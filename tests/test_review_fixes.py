"""Fixes from the end-to-end review: turn numbering, rewound cards, wording."""

from unittest.mock import MagicMock, patch

from neow.cli.commands import parse_command
from neow.core.approval import ApprovalMode, ApprovalPolicy, ApprovalTier
from neow.core.checkpoints import CheckpointStore
from neow.tui.screens.chat import ChatScreen
from neow.tui.widgets.cards import AssistantCard, SystemCard, UserCard
from tests.tui.conftest import Chunk, FakeConversation, _chat_app


def test_approval_reasons_are_chinese():
    write = ApprovalPolicy(mode=ApprovalMode.WRITE)
    assert write.check_approval("edit_file", tier=ApprovalTier.WRITE).reason == (
        "写入操作需要确认：edit_file"
    )
    assert write.check_approval("execute_command", tier=ApprovalTier.EXEC).reason == (
        "执行命令操作需要确认：execute_command"
    )
    assert "危险操作" in write.check_approval("x", is_dangerous=True).reason
    ask = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
    assert ask.check_approval("read_file", tier=ApprovalTier.READ).reason.startswith(
        "always-ask 模式"
    )
    override = ApprovalPolicy(tool_overrides={"grep": "deny", "glob": "prompt"})
    assert override.check_approval("grep").reason == "按配置禁止使用 grep"
    assert override.check_approval("glob").reason == "按配置 glob 每次都需确认"


def _repl(conversation, inputs):
    from neow.cli.repl import REPL

    config = MagicMock()
    config.web = {"enabled": False, "auto_detect": False}
    plugin_api = MagicMock()
    plugin_api.plugin_commands = {"/hello": MagicMock()}
    repl = REPL(conversation, config=config, streaming=False, plugin_api=plugin_api)
    printed = []
    with (
        patch.object(repl, "_get_input", side_effect=[*inputs, EOFError]),
        patch(
            "neow.cli.repl.print_user_message",
            lambda text, msg_num=None, timestamp=None: printed.append((text, msg_num)),
        ),
        patch.object(repl, "_handle_command", wraps=repl._handle_command),
        patch("neow.cli.repl.print_error") as errors,
    ):
        repl.start()
    return repl, plugin_api, printed, errors


def test_repl_numbers_turns_like_rewind_and_keeps_commands_local(tmp_path):
    conversation = MagicMock()
    conversation.pending_lint_feedback = None
    conversation.checkpoints = CheckpointStore(root=tmp_path, session_id="s")
    conversation.checkpoints.begin_turn("earlier", 0)  # next turn will be #2
    sent = []
    conversation.get_response.side_effect = lambda text: sent.append(text) or (
        MagicMock(content="ok")
    )
    repl, plugin_api, printed, errors = _repl(
        conversation, ["/hello world", "/typo", "question"]
    )
    # Commands are not turns: no number, never sent to the model.
    assert printed[0] == ("> /hello world", None)
    assert printed[1] == ("> /typo", None)
    plugin_api.plugin_commands["/hello"].assert_called_once_with("world")
    errors.assert_called_once_with("Unknown command: /typo")
    # The prompt gets the checkpoint's number.
    assert printed[2] == ("> question", 2)
    assert sent == ["question"]


async def test_tui_greys_out_rewound_turns(tmp_path):
    store = CheckpointStore(root=tmp_path, session_id="s")

    class Conversation(FakeConversation):
        def get_response_stream(self, user_input, cancel=None):
            # Like AgentLoop: open the checkpoint, then add the turn's messages.
            store.begin_turn(user_input, len(self.messages))
            self.messages += [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": f"re: {user_input}"},
            ]
            yield Chunk(content_delta=f"re: {user_input}")

    conversation = Conversation(script=[])
    conversation.checkpoints = store
    app = _chat_app(conversation)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        for prompt in ("first", "second", "third"):
            screen.submit_prompt(prompt)
            for _ in range(30):
                await pilot.pause()
                if not screen._busy:
                    break
        users = list(screen.query(UserCard))
        assert ["#1" in u.title_text() for u in users] == [True, False, False]
        assert "#3" in users[2].title_text()  # numbers follow the checkpoints

        result = screen.commands.dispatch(parse_command("/rewind 2"))
        await pilot.pause()
        assert "对话已回退" in result.text and len(conversation.messages) == 2
        assistants = list(screen.query(AssistantCard))
        assert [u.rewound for u in users] == [False, True, True]
        assert [a.rewound for a in assistants] == [False, True, True]
        assert (
            "已回退" in users[1].title_text() and "已回退" not in users[0].title_text()
        )
        assert not any(c.rewound for c in screen.query(SystemCard))

        # A new turn after the rewind is numbered #2 again and stays normal.
        screen.submit_prompt("again")
        for _ in range(30):
            await pilot.pause()
            if not screen._busy:
                break
        newest = list(screen.query(UserCard))[-1]
        assert "#2" in newest.title_text() and not newest.rewound
