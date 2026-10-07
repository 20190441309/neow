"""PTY command smoke: /help, /model picker, /diff screen (goal task t7).

Run: ``.venv/bin/python tests/tui/pty_commands.py``
Prints ``PTY COMMANDS OK`` and saves the raw terminal output.
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

STEPS = [
    ("/help\r", "斜杠命令"),
    ("\x1b", None),  # escape help screen
    ("/diff\r", "DIFF"),
    ("\x1b", None),  # escape diff screen
    ("/model\r", "选择模型"),
    ("\x1b", None),  # escape picker
]


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def main() -> int:
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.tui._fake_launcher"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=REPO,
        close_fds=True,
    )
    os.close(slave)
    raw = bytearray()
    for payload, needle in STEPS:
        deadline = time.time() + 12.0
        sent = False
        last_send = 0.0
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    raw.extend(os.read(master, 65536))
                except OSError:
                    break
            text = strip_ansi(raw.decode("utf-8", errors="replace"))
            if needle is None:
                break
            if needle in text:
                break
            # Resend until raw mode is ready / command lands.
            if time.time() - last_send > 3.0:
                os.write(master, payload.encode("utf-8"))
                last_send = time.time()
                sent = True
            if proc.poll() is not None:
                break
        if needle is not None:
            text = strip_ansi(raw.decode("utf-8", errors="replace"))
            if needle not in text:
                proc.kill()
                raise AssertionError(f"missing {needle!r}; tail={text[-400:]!r}")
        if needle is None and not sent:
            os.write(master, payload.encode("utf-8"))
        time.sleep(0.5)

    os.write(master, b"\x11")  # Ctrl+Q
    for _ in range(25):
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if proc.poll() is None:
        proc.kill()
    proc.wait()
    os.close(master)

    text = strip_ansi(raw.decode("utf-8", errors="replace"))
    evidence = os.path.join(REPO, ".superpowers", "pty-commands-output.txt")
    with open(evidence, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("PTY COMMANDS OK")
    print("evidence:", evidence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
