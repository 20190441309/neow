"""PTY observation: drive the TUI with a fake stream and capture rendering.

Evidence for goal task t6: a real terminal session shows the scramble
thinking card, the streamed assistant text and the completed turn.

Run: ``.venv/bin/python tests/tui/pty_observe.py``
Prints ``PTY OBSERVE OK`` and saves the raw terminal output.
"""

import os
import pty
import re
import select
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPT = "修复 grep_code".encode("utf-8")
NEEDLES = ["分析问题中", "fake response"]
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[=>]")


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
    output = bytearray()
    start = time.time()
    sent = False
    last_send = 0.0
    deadline = start + 30.0
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            output.extend(chunk)
        if time.time() - start > 2.0 and (not sent or time.time() - last_send > 5.0):
            os.write(master, PROMPT + b"\r")
            sent = True
            last_send = time.time()
        text = strip_ansi(output.decode("utf-8", errors="replace"))
        if sent and all(needle in text for needle in NEEDLES):
            break
        if proc.poll() is not None:
            break

    text = strip_ansi(output.decode("utf-8", errors="replace"))
    ok = all(needle in text for needle in NEEDLES)
    evidence = os.path.join(REPO, ".superpowers", "pty-observe-output.txt")
    try:
        os.makedirs(os.path.dirname(evidence), exist_ok=True)
        with open(evidence, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass

    if proc.poll() is None:
        os.write(master, b"\x11")  # Ctrl+Q to quit
        for _ in range(20):
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        if proc.poll() is None:
            proc.kill()
    proc.wait()
    os.close(master)

    if not ok:
        missing = [n for n in NEEDLES if n not in text]
        raise AssertionError(
            f"PTY observe failed; missing {missing}; tail={text[-500:]!r}"
        )
    print("PTY OBSERVE OK")
    print("evidence:", evidence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
