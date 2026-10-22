#!/usr/bin/env python3
"""Verify the Muse wrapper stages a hash-pinned launcher in a writable home."""
from hashlib import sha256
from pathlib import Path
import os
import re
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "docker/paseo-muse-launcher.sh"
SOURCE_PATH = "/usr/local/share/paseo-muse-launcher.sh"

with tempfile.TemporaryDirectory(prefix="paseo-muse-wrapper-") as tmp:
    root = Path(tmp)
    source = root / "official-launcher.sh"
    source.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$HOME/invoked.args\"\n",
        encoding="utf-8",
    )
    digest = sha256(source.read_bytes()).hexdigest()
    wrapper = WRAPPER.read_text(encoding="utf-8")
    wrapper = wrapper.replace(SOURCE_PATH, str(source))
    wrapper = re.sub(
        r"expected_sha256=[0-9a-f]{64}",
        f"expected_sha256={digest}",
        wrapper,
        count=1,
    )
    test_wrapper = root / "muse-wrapper.sh"
    test_wrapper.write_text(wrapper, encoding="utf-8")
    home = root / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)

    for argument in ("--first-check", "--second-check"):
        result = subprocess.run(
            ["/bin/sh", str(test_wrapper), argument],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise SystemExit(f"Muse wrapper failed: {result.stderr.strip()}")
        if (home / "invoked.args").read_text(encoding="utf-8").strip() != argument:
            raise SystemExit("Muse wrapper did not pass arguments to the staged launcher")
        staged = home / ".local/bin/muse-launcher"
        if sha256(staged.read_bytes()).hexdigest() != digest:
            raise SystemExit("staged Muse launcher hash does not match the pinned source")
        if stat.S_IMODE(staged.stat().st_mode) != 0o755:
            raise SystemExit("staged Muse launcher is not executable")
        if argument == "--second-check":
            break
        staged.write_text("tampered\n", encoding="utf-8")

print("muse_launcher_wrapper_test=passed")
