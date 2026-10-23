#!/usr/bin/env python3
"""Smoke-test persistent provider config ownership repair as root."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker/paseo-agent-config-permissions.sh"
DELEGATE = 'exec /usr/bin/tini -- /usr/local/bin/paseo-docker-entrypoint "$@"'
ROOT_DELEGATE = 'exec /usr/bin/tini -- /usr/sbin/gosu paseo /usr/local/bin/paseo-docker-entrypoint "$@"'

if os.geteuid() != 0:
    raise SystemExit("run this test as root (CI invokes it with sudo)")

script = ENTRYPOINT.read_text(encoding="utf-8")
if script.count(DELEGATE) != 1:
    raise SystemExit("expected exactly one delegation to Paseo's original entrypoint")
if script.count(ROOT_DELEGATE) != 1:
    raise SystemExit('expected privilege drop before upstream directory preparation')
HOME_ASSIGNMENT = "home=/home/paseo"
if script.count(HOME_ASSIGNMENT) != 1:
    raise SystemExit("expected exactly one fixed Paseo home assignment")

with tempfile.TemporaryDirectory(prefix="paseo-permissions-") as tmp:
    root = Path(tmp)
    root.chmod(0o755)  # Allow the UID 1000 access check to traverse the fixture.
    home = root / "home"
    test_script = script.replace('/usr/bin/python3', sys.executable).replace(
        '/usr/local/libexec/paseo-repair-permissions.py',
        str(ROOT / 'docker/paseo-repair-permissions.py'),
    ).replace(ROOT_DELEGATE, "exit 0").replace(DELEGATE, "exit 0").replace(
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
    gh = xdg / "gh"
    (gh / "nested").mkdir(parents=True)
    for path in (gh / "config.yml", gh / "hosts.yml", gh / "nested" / "state.yml"):
        path.write_text("{}\n", encoding="utf-8")
        path.chmod(0o000)
    gh.chmod(0o000)
    (gh / "nested").chmod(0o000)
    xdg.chmod(0o000)
    home.chmod(0o000)
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
    marker.chmod(0o640)
    (home / ".aider-external").symlink_to(outside, target_is_directory=True)
    (gh / "external-file").symlink_to(marker)
    (gh / "external-directory").symlink_to(outside, target_is_directory=True)

    env = os.environ.copy()
    env.update({
        "PASEO_PASSWORD": "test-fixture-only",
        "HOME": str(home),
        "CODEX_HOME": str(codex),
        "CLAUDE_CONFIG_DIR": str(claude),
        "XDG_CONFIG_HOME": str(xdg),
        "XDG_DATA_HOME": str(xdg_data),
        "GH_CONFIG_DIR": str(gh),
    })
    result = subprocess.run(["/bin/sh", "-c", test_script], env=env, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(f"entrypoint smoke test failed: {result.stderr.strip()}")

    owned_paths = [home, gh, gh / "config.yml", gh / "hosts.yml",
                   gh / "nested", gh / "nested" / "state.yml",
                   codex, codex / "tmp", codex / "config.toml", claude,
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
                           (home / ".claude.json", 0o600),
                           (gh, 0o700), (gh / "nested", 0o700),
                           (gh / "config.yml", 0o600), (gh / "hosts.yml", 0o600),
                           (gh / "nested" / "state.yml", 0o600)]:
        mode = path.stat().st_mode & 0o777
        if mode != expected:
            raise SystemExit(f"wrong mode for {path.name}: {mode:o}, expected {expected:o}")
    st = marker.stat()
    if (st.st_uid, st.st_gid) != (0, 0):
        raise SystemExit("symlink target ownership was unexpectedly changed")
    if st.st_mode & 0o777 != 0o640:
        raise SystemExit("symlink target permissions were unexpectedly changed")
    # Verify actual access as Paseo's UID, not just mode bits observed by root.
    access_check = (
        "from pathlib import Path; import sys; "
        "p = Path(sys.argv[1]); p.read_text(); "
        "p.write_text('verified: true\\n')"
    )
    subprocess.run(
        [sys.executable, "-c", access_check, str(gh / "config.yml")],
        user=1000, group=1000, extra_groups=[], check=True,
    )
    subprocess.run(["/bin/sh", "-c", test_script], env=env, check=True)

print("permission_entrypoint_smoke_test=passed")
