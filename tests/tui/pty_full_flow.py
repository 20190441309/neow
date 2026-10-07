"""PTY full-flow smoke: start, prompt, tool call, approval, response, exit.

Sets ``NEOW_FAKE_TOOLS=1`` so the fake stream requests an ``ls`` tool call;
the TUI shows the approval modal, this script presses ``y``, then waits for
the tool card and the streamed response before quitting.

Run: ``.venv/bin/python tests/tui/pty_full_flow.py``
Prints ``PTY FULL FLOW OK`` and saves the raw terminal output.
"""

import os
import pty
import re
import select
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[=>]")
PROMPT = "列出文件".encode("utf-8")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def main() -> int:
    master, slave = pty.openpty()
    env = os.environ.copy()
    env["NEOW_FAKE_TOOLS"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.tui._fake_launcher"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=REPO,
        env=env,
        close_fds=True,
    )
    os.close(slave)
    raw = bytearray()
    start = time.time()
    sent_prompt = False
    approved = False
    last_prompt_send = 0.0

    def text() -> str:
        return strip_ansi(raw.decode("utf-8", errors="replace"))

    deadline = start + 45.0
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                raw.extend(os.read(master, 65536))
            except OSError:
                break
        current = text()
        # Send the prompt once the app has painted.
        if not sent_prompt and "NEOW" in current and time.time() - start > 2.0:
            os.write(master, PROMPT + b"\r")
            sent_prompt = True
            last_prompt_send = time.time()
        elif not sent_prompt and time.time() - last_prompt_send > 5.0:
            os.write(master, PROMPT + b"\r")
            last_prompt_send = time.time()
        # Approve the tool call once the modal is up.
        if sent_prompt and not approved and "审批请求" in current:
            os.write(master, b"y")
            approved = True
        if approved and "fake response" in current and "execute_command" in current:
            break
        if proc.poll() is not None:
            break

    current = text()
    os.write(master, b"\x11")  # Ctrl+Q
    for _ in range(25):
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if proc.poll() is None:
        proc.kill()
    proc.wait()
    os.close(master)

    missing = [
        needle
        for needle in ("审批请求", "execute_command", "fake response")
        if needle not in current
    ]
    evidence = os.path.join(REPO, ".superpowers", "pty-full-flow-output.txt")
    with open(evidence, "w", encoding="utf-8") as handle:
        handle.write(current)
    if missing:
        raise AssertionError(f"missing {missing}; tail={current[-500:]!r}")
    print("PTY FULL FLOW OK")
    print("evidence:", evidence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
