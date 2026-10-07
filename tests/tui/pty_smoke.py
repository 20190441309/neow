"""PTY smoke test: TUI / --plain / one-shot with a fake model client.

Run: ``.venv/bin/python tests/tui/pty_smoke.py``
Prints ``PTY SMOKE OK`` and exits 0 on success.
"""

import os
import pty
import select
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_pty(args, *, send=b"", delay=2.0, interval=0.8, timeout=25.0):
    """Spawn the fake launcher in a pty; resend *send* until the process exits.

    The first key can arrive before Textual has entered raw mode, so the
    keystroke is repeated at *interval* seconds until the child exits.
    """

    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.tui._fake_launcher", *args],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=REPO,
        close_fds=True,
    )
    os.close(slave)
    output = bytearray()
    start = time.time()
    next_send = start + delay
    while time.time() - start < timeout:
        if send and time.time() >= next_send:
            try:
                os.write(master, send)
            except OSError:
                pass
            next_send = time.time() + interval
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            output.extend(chunk)
        if proc.poll() is not None:
            break
    if proc.poll() is None:
        proc.kill()
        proc.wait()
        os.close(master)
        raise AssertionError(
            f"TIMEOUT: neow {args} did not exit; tail={bytes(output[-300:])!r}"
        )
    os.close(master)
    return proc.returncode, bytes(output)


def main() -> int:
    # 1) TUI (default): Ctrl+Q quits.
    code, out = run_pty([], send=b"\x11", delay=2.5)
    assert code == 0, (code, out[-400:])

    # 2) Classic REPL: Ctrl+D exits.
    code, out = run_pty(["--plain"], send=b"\x04", delay=2.5)
    assert code == 0, (code, out[-400:])

    # 3) One-shot: prints the fake response and exits.
    code, out = run_pty(["hi"], timeout=25.0)
    assert code == 0, (code, out[-400:])
    assert b"fake response" in out, out[-400:]

    print("PTY SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
