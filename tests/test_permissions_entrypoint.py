#!/usr/bin/env python3
"""Smoke-test persistent provider config ownership repair as root."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker/paseo-agent-config-permissions.sh"
DELEGATE = 'exec /usr/bin/tini -- /usr/local/bin/paseo-docker-entrypoint "$@"'

if os.geteuid() != 0:
    raise SystemExit("run this test as root (CI invokes it with sudo)")

script = ENTRYPOINT.read_text(encoding="utf-8")
if script.count(DELEGATE) != 1:
    raise SystemExit("expected exactly one delegation to Paseo's original entrypoint")
HOME_ASSIGNMENT = "home=/home/paseo"
if script.count(HOME_ASSIGNMENT) != 1:
    raise SystemExit("expected exactly one fixed Paseo home assignment")

with tempfile.TemporaryDirectory(prefix="paseo-permissions-") as tmp:
    root = Path(tmp)
    home = root / "home"
    test_script = script.replace(DELEGATE, "exit 0").replace(
        HOME_ASSIGNMENT, f"home={home}"
    )
    codex = home / ".codex"
    (codex / "tmp").mkdir(parents=True)
    (codex / "config.toml").write_text("model = 'test'\n", encoding="utf-8")
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / ".credentials.json").write_text("{}\n", encoding="utf-8")
    (home / ".claude.json").write_text("{}\n", encoding="utf-8")
    xdg = home / ".config"
    (xdg / "opencode").mkdir(parents=True)
    (xdg / "opencode" / "settings.json").write_text("{}\n", encoding="utf-8")
    (xdg / "github-copilot").mkdir()
    (xdg / "github-copilot" / "hosts.json").write_text("{}\n", encoding="utf-8")
    pi = home / ".pi" / "agent"
    pi.mkdir(parents=True)
    (pi / "auth.json").write_text("{}\n", encoding="utf-8")
    (home / ".omp").mkdir()
    (home / ".omp" / "settings.json").write_text("{}\n", encoding="utf-8")
    (home / ".gemini").mkdir()
    (home / ".aider.conf.yml").write_text("test: true\n", encoding="utf-8")
    (home / ".opencode").mkdir()
    xdg_data = home / ".local" / "share"
    (xdg_data / "opencode").mkdir(parents=True)
    (xdg_data / "opencode" / "auth.json").write_text("{}\n", encoding="utf-8")
    (xdg_data / "muse").mkdir()
    (xdg_data / "muse" / "state.json").write_text("{}\n", encoding="utf-8")
    (home / ".custom-provider").mkdir()
    (home / ".custom-provider" / "auth.json").write_text("{}\n", encoding="utf-8")
    outside = root / "outside"
    outside.mkdir()
    marker = outside / "keep-root-owned"
    marker.write_text("marker\n", encoding="utf-8")
    (home / ".aider-external").symlink_to(outside, target_is_directory=True)

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "CODEX_HOME": str(codex),
        "CLAUDE_CONFIG_DIR": str(claude),
        "XDG_CONFIG_HOME": str(xdg),
        "XDG_DATA_HOME": str(xdg_data),
    })
    result = subprocess.run(["/bin/sh", "-c", test_script], env=env, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(f"entrypoint smoke test failed: {result.stderr.strip()}")

    owned_paths = [home, codex, codex / "tmp", codex / "config.toml", claude,
                   claude / ".credentials.json", home / ".claude.json", xdg,
                   xdg / "opencode" / "settings.json",
                   xdg / "github-copilot" / "hosts.json", pi,
                   pi / "auth.json", home / ".omp", home / ".omp" / "settings.json",
                   home / ".gemini", home / ".aider.conf.yml", home / ".opencode",
                   xdg_data, xdg_data / "opencode" / "auth.json",
                   xdg_data / "muse" / "state.json",
                   home / ".custom-provider" / "auth.json"]
    for path in owned_paths:
        st = path.stat()
        if (st.st_uid, st.st_gid) != (1000, 1000):
            raise SystemExit(f"wrong owner for {path.name}: {st.st_uid}:{st.st_gid}")
    for path, expected in [(codex, 0o700), (codex / "tmp", 0o700),
                           (claude, 0o700), (codex / "config.toml", 0o600),
                           (home / ".claude.json", 0o600)]:
        mode = path.stat().st_mode & 0o777
        if mode != expected:
            raise SystemExit(f"wrong mode for {path.name}: {mode:o}, expected {expected:o}")
    st = marker.stat()
    if (st.st_uid, st.st_gid) != (0, 0):
        raise SystemExit("symlink target ownership was unexpectedly changed")

print("permission_entrypoint_smoke_test=passed")
