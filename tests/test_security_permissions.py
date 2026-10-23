"""Root init regressions: descriptor identity, links, races and nested mounts."""
import importlib.util
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('repair', Path(__file__).resolve().parents[1] / 'docker/paseo-repair-permissions.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


@unittest.skipUnless(os.geteuid() == 0, 'requires root to verify ownership boundaries')
class SecurityPermissionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.outside = self.root / 'outside'
        self.outside.mkdir()
        self.marker = self.outside / 'marker'
        self.marker.write_text('non-secret fixture')
        self.marker.chmod(0o640)

    def assert_outside_untouched(self):
        self.assertEqual(self.marker.stat().st_uid, 0)
        self.assertEqual(self.marker.stat().st_mode & 0o777, 0o640)

    def test_file_replaced_with_link_after_stat(self):
        candidate = self.home / 'candidate'
        candidate.touch()
        real_open = os.open

        def racing_open(path, flags, *args, **kwargs):
            if path == 'candidate':
                candidate.unlink()
                candidate.symlink_to(self.marker)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(repair.os, 'open', side_effect=racing_open):
            repair.Repair(self.home, {}).run()
        self.assert_outside_untouched()

    def test_ancestor_replaced_with_link_after_stat(self):
        config = self.home / '.config'
        config.mkdir()
        real_open = os.open

        def racing_open(path, flags, *args, **kwargs):
            if path == '.config':
                config.rename(self.home / 'old-config')
                config.symlink_to(self.outside, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(repair.os, 'open', side_effect=racing_open):
            repair.Repair(self.home, {}).run()
        self.assert_outside_untouched()

    def test_hardlink_does_not_change_external_inode(self):
        gh = self.home / '.config/gh'
        gh.mkdir(parents=True)
        os.link(self.marker, gh / 'config.yml')
        repair.Repair(self.home, {}).run()
        self.assert_outside_untouched()

    def test_mount_identity_is_checked_even_on_same_device(self):
        nested = self.home / 'nested'
        nested.mkdir()
        marker = nested / 'file'
        marker.touch()
        actual_mount_id = repair.mount_id

        def simulated_mount_id(fd):
            current = os.readlink(f'/proc/self/fd/{fd}')
            return actual_mount_id(fd) + (1 if current == str(nested) else 0)

        with patch.object(repair, 'mount_id', side_effect=simulated_mount_id):
            repair.Repair(self.home, {}).run()
        self.assertEqual(nested.stat().st_uid, 0)
        self.assertEqual(marker.stat().st_uid, 0)

    def test_config_outside_home_is_never_repaired(self):
        repair.Repair(self.home, {'GH_CONFIG_DIR': str(self.outside)}).run()
        self.assert_outside_untouched()

    def test_home_with_symlink_ancestor_is_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            repair.Repair(alias / 'home', {}).run()
        self.assert_outside_untouched()

    def test_mount_verification_failure_stops_repair(self):
        with patch.object(repair, 'mount_id', side_effect=OSError('proc unavailable')):
            with self.assertRaises(OSError):
                repair.Repair(self.home, {}).run()

    def test_privileged_python_ignores_workspace_import_hooks(self):
        attack = self.root / 'untrusted-python'
        attack.mkdir()
        marker = self.root / 'hook-executed'
        (attack / 'sitecustomize.py').write_text(
            'import os\nopen(os.environ["PWN_MARKER"], "w").write("executed")\n')
        env = dict(os.environ, PYTHONPATH=str(attack), PWN_MARKER=str(marker))
        subprocess.run([sys.executable, '-I', '-S', str(Path(repair.__file__)), str(self.home)],
                       env=env, check=True)
        self.assertFalse(marker.exists())

    def test_daemon_without_password_is_rejected_before_repair(self):
        entrypoint = Path(__file__).resolve().parents[1] / 'docker/paseo-agent-config-permissions.sh'
        env = dict(os.environ)
        env.pop('PASEO_PASSWORD', None)
        result = subprocess.run(['/bin/sh', str(entrypoint)], env=env,
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PASEO_PASSWORD is required', result.stderr)


if __name__ == '__main__':
    unittest.main()
