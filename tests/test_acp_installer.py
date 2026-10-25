"""ACP packaging and configuration regressions, without network or provider login."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location(
    'paseo_acp', Path(__file__).resolve().parents[1] / 'docker/paseo-acp.py')
acp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acp)


class AcpInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('ROOT', self.root / 'install'), ('BIN', self.root / 'bin'), ('DEPS', self.root / 'locks')]:
            mock = patch.object(acp, name, value)
            mock.start()
            self.addCleanup(mock.stop)
            value.mkdir()

    def npm_fixture(self):
        lock = {'lockfileVersion': 3, 'packages': {
            '': {'name': 'test-agent', 'version': '1.0.0', 'dependencies': {'example-agent': '1.2.3'}},
            'node_modules/example-agent': {'version': '1.2.3', 'integrity': 'sha512-reviewed',
                'bin': {'example-agent': 'bin/agent'},
                'resolved': 'https://registry.npmjs.org/example-agent/-/example-agent-1.2.3.tgz'},
        }}
        return lock

    def locked_dist(self, lock):
        data = json.dumps(lock).encode()
        (acp.DEPS / 'test.json').write_bytes(data)
        return {'package': 'example-agent@1.2.3', 'bin': 'example-agent',
                'integrity': 'sha512-reviewed',
                'lock': {'path': 'test.json', 'sha256': hashlib.sha256(data).hexdigest()}}

    def test_archive_cannot_escape_installation(self):
        archive = self.root / 'bad.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            entry = tarfile.TarInfo('../outside')
            entry.size = 4
            output.addfile(entry, io.BytesIO(b'evil'))
        with self.assertRaises(ValueError):
            acp.extract(archive, acp.ROOT)
        self.assertFalse((self.root / 'outside').exists())
        with zipfile.ZipFile(self.root / 'bad.zip', 'w') as output:
            output.writestr('../outside', b'evil')
        with self.assertRaises(ValueError):
            acp.extract(self.root / 'bad.zip', acp.ROOT)

    def test_zip_symlink_cannot_escape(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            entry = zipfile.ZipInfo('escape')
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            output.writestr(entry, '../../outside')
        with self.assertRaises(ValueError):
            acp.extract(archive, acp.ROOT)

    def test_tar_rejects_external_links_and_devices(self):
        for kind, target in [(tarfile.SYMTYPE, '../../outside'),
                             (tarfile.LNKTYPE, '/etc/passwd'), (tarfile.FIFOTYPE, '')]:
            archive = self.root / 'bad.tar'
            with tarfile.open(archive, 'w') as output:
                member = tarfile.TarInfo('untrusted')
                member.type, member.linkname = kind, target
                output.addfile(member)
            with self.assertRaises(ValueError):
                acp.extract(archive, acp.ROOT)

    def test_tar_keeps_internal_links_and_strips_special_modes(self):
        archive = self.root / 'valid.tar'
        with tarfile.open(archive, 'w') as output:
            member = tarfile.TarInfo('agent')
            member.size, member.mode = 3, 0o6777
            output.addfile(member, io.BytesIO(b'bin'))
            for name, kind in [('alias', tarfile.SYMTYPE), ('hard', tarfile.LNKTYPE)]:
                link = tarfile.TarInfo(name)
                link.type, link.linkname = kind, 'agent'
                output.addfile(link)
        acp.extract(archive, acp.ROOT)
        self.assertEqual((acp.ROOT / 'agent').stat().st_mode & 0o7777, 0o755)
        self.assertEqual((acp.ROOT / 'hard').read_bytes(), b'bin')
        self.assertTrue((acp.ROOT / 'alias').is_symlink())

    def test_download_rejects_bad_checksum(self):
        response = io.BytesIO(b'wrong archive')
        response.url = 'https://example.org/agent'
        with patch.object(acp, 'urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                acp.download(response.url, self.root / 'download', '0' * 64)

    def test_missing_hash_is_rejected_before_network(self):
        with patch.object(acp, 'urlopen') as network:
            for digest in (None, '', 'not-a-hash'):
                with self.assertRaisesRegex(ValueError, 'reviewed SHA-256'):
                    acp.download('https://example.org/binary', self.root / 'download', digest)
        network.assert_not_called()

    def test_unverified_binary_is_not_installed(self):
        entry = {'id': 'unverified', 'distribution': {'binary': {'linux-x86_64': {
            'archive': 'https://example.org/binary', 'cmd': './agent'}}}}
        with patch.object(acp, 'download') as network:
            result = acp.install_agent(entry, 'linux-x86_64')
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('SHA-256 missing', result['reason'])
        network.assert_not_called()

    def test_archive_expansion_is_bounded(self):
        archive = self.root / 'bomb.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('big', b'12345')
        with patch.object(acp, 'MAX_EXPANDED_BYTES', 4):
            with self.assertRaisesRegex(ValueError, 'exceeds limits'):
                acp.extract(archive, acp.ROOT)
        self.assertFalse((acp.ROOT / 'big').exists())

    def test_wrapper_preserves_arguments_and_environment(self):
        acp.wrapper('agent', ['/bin/sh', '-c', 'printf "%s\\n" "$MODE" "$@"', 'agent'],
                    {'MODE': "a value with 'quotes'"})
        output = subprocess.check_output([str(acp.BIN / 'agent'), 'a b', '$(exit 1)'], text=True)
        self.assertEqual(output.splitlines(), ["a value with 'quotes'", 'a b', '$(exit 1)'])
        output = subprocess.check_output([str(acp.BIN / 'agent')], text=True,
                                         env={**os.environ, 'MODE': 'user override'})
        self.assertEqual(output.strip(), 'user override')

    def test_missing_arm_distribution_is_reported(self):
        entry = {'id': 'amd-only', 'distribution': {'binary': {'linux-x86_64': {}}}}
        result = acp.install_agent(entry, 'linux-aarch64')
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('linux-aarch64', result['reason'])
        self.assertFalse((acp.BIN / 'paseo-acp-amd-only').exists())

    def test_npm_checksum_is_checked_before_install_scripts(self):
        directory = acp.ROOT / 'npm-agent'
        lock = self.npm_fixture()
        lock['packages']['node_modules/example-agent']['integrity'] = 'sha512-unexpected'
        dist = self.locked_dist(lock)
        with patch.object(acp, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'integrity differs'):
                acp.install_npm(dist, directory)
        run.assert_not_called()

    def test_mutated_lock_is_rejected_before_npm(self):
        dist = self.locked_dist(self.npm_fixture())
        (acp.DEPS / 'test.json').write_text('{}')
        with patch.object(acp, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'lock checksum mismatch'):
                acp.install_npm(dist, acp.ROOT / 'agent')
        run.assert_not_called()

    def test_npm_build_uses_committed_graph_without_resolving(self):
        dist = self.locked_dist(self.npm_fixture())
        directory = acp.ROOT / 'agent'

        def fake_ci(*args):
            executable = directory / 'node_modules/example-agent/bin/agent'
            executable.parent.mkdir(parents=True)
            executable.write_text('#!/bin/sh\nexit 0\n')
            executable.chmod(0o755)

        with patch.object(acp, 'run', side_effect=fake_ci) as run:
            executable = acp.install_npm(dist, directory)
        self.assertEqual(executable, directory / 'node_modules/example-agent/bin/agent')
        self.assertFalse((directory / 'node_modules/.bin/example-agent').exists())
        self.assertEqual(run.call_args.args[:2], ('npm', 'ci'))
        self.assertNotIn('install', run.call_args.args)
        self.assertEqual((directory / 'package-lock.json').read_bytes(), (acp.DEPS / 'test.json').read_bytes())

    def test_npm_transitive_without_integrity_is_rejected(self):
        lock = self.npm_fixture()
        lock['packages']['node_modules/unsafe'] = {'version': '2.0.0'}
        dist = self.locked_dist(lock)
        with patch.object(acp, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Unverified npm dependency'):
                acp.install_npm(dist, acp.ROOT / 'agent')
        run.assert_not_called()

    def test_npm_preflight_preserves_overrides_without_install_scripts(self):
        lock = self.npm_fixture()
        lock['packages']['']['overrides'] = {'example-agent': {'uuid': '11.1.1'}}
        dist = self.locked_dist(lock)

        def check_ci(*args, **kwargs):
            self.assertEqual(args[:2], ('npm', 'ci'))
            self.assertIn('--dry-run', args)
            self.assertIn('--ignore-scripts', args)
            directory = Path(args[args.index('--prefix') + 1])
            root = json.loads((directory / 'package.json').read_text())
            self.assertEqual(root['overrides'], lock['packages']['']['overrides'])

        with patch.object(acp, 'run', side_effect=check_ci) as run:
            acp.check_locks({'agents': []}, {'packages': [dist]})
        run.assert_called_once()

    def test_nova_override_matches_verified_bundled_uuid(self):
        root = Path(__file__).resolve().parents[1]
        lock = json.loads((root / 'docker/dependency-locks/npm/nova.json').read_text())
        package = 'node_modules/@compass-ai/nova'
        bundled = lock['packages'][package + '/node_modules/exceljs/node_modules/uuid']
        override = lock['packages']['']['overrides']['@compass-ai/nova']['exceljs']['uuid']
        self.assertTrue(bundled['inBundle'])
        self.assertEqual(override, bundled['version'])
        self.assertEqual(override, '11.1.1')

    def test_npm_unreviewed_bin_is_rejected_before_install(self):
        dist = self.locked_dist(self.npm_fixture())
        dist['bin'] = 'unreviewed'
        with patch.object(acp, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'absent from reviewed lock'):
                acp.install_npm(dist, acp.ROOT / 'agent')
        run.assert_not_called()

    def test_npm_bin_cannot_escape_package(self):
        lock = self.npm_fixture()
        lock['packages']['node_modules/example-agent']['bin']['example-agent'] = '../outside'
        dist = self.locked_dist(lock)
        with patch.object(acp, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'escapes installation'):
                acp.install_npm(dist, acp.ROOT / 'agent')
        run.assert_not_called()

    def test_npm_missing_actual_bin_still_fails(self):
        dist = self.locked_dist(self.npm_fixture())
        with patch.object(acp, 'run'):
            with self.assertRaisesRegex(ValueError, 'Missing npm executable'):
                acp.install_npm(dist, acp.ROOT / 'agent')

    def test_npm_postinstall_cannot_redirect_package(self):
        dist = self.locked_dist(self.npm_fixture())
        directory = acp.ROOT / 'agent'
        outside = self.root / 'outside'
        (outside / 'bin').mkdir(parents=True)
        (outside / 'bin/agent').touch(mode=0o755)

        def fake_ci(*args):
            modules = directory / 'node_modules'
            modules.mkdir()
            (modules / 'example-agent').symlink_to(outside, target_is_directory=True)

        with patch.object(acp, 'run', side_effect=fake_ci):
            with self.assertRaisesRegex(ValueError, 'package directory was redirected'):
                acp.install_npm(dist, directory)

    def test_bundled_dependency_is_covered_by_verified_parent(self):
        lock = self.npm_fixture()
        lock['packages']['node_modules/example-agent/node_modules/bundled'] = {
            'version': '2.0.0', 'inBundle': True}
        dist = self.locked_dist(lock)
        directory = acp.ROOT / 'agent'

        def fake_ci(*args):
            executable = directory / 'node_modules/example-agent/bin/agent'
            executable.parent.mkdir(parents=True)
            executable.touch()
            executable.chmod(0o755)

        with patch.object(acp, 'run', side_effect=fake_ci) as run:
            acp.install_npm(dist, directory)
        run.assert_called_once()

    def test_bundled_flag_without_verified_parent_cannot_bypass_hashes(self):
        lock = self.npm_fixture()
        lock['packages']['node_modules/unrelated/node_modules/bundled'] = {
            'version': '2.0.0', 'inBundle': True}
        dist = self.locked_dist(lock)
        with patch.object(acp, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Unverified npm dependency'):
                acp.install_npm(dist, acp.ROOT / 'agent')
        run.assert_not_called()

    def test_wrapper_rejects_shell_syntax_in_metadata_keys(self):
        with self.assertRaisesRegex(ValueError, 'environment variable'):
            acp.wrapper('safe', ['/bin/true'], {'X;touch injected': 'value'})
        self.assertFalse((acp.BIN / 'safe').exists())
        with self.assertRaisesRegex(ValueError, 'wrapper name'):
            acp.wrapper('../outside', ['/bin/true'])

    def test_install_refuses_root(self):
        with patch.object(acp.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'unprivileged build'):
                acp.install({'agents': []}, 'amd64')

    def test_source_backend_uses_hashes_and_disables_implicit_dependency_install(self):
        backend = self.locked_dist(self.npm_fixture())['lock']
        checkout = acp.ROOT / 'source'
        checkout.mkdir()
        with patch.object(acp, 'run') as run:
            acp.build_source(checkout, {'buildLock': backend, 'python': '3.14.9', 'extra': 'acp'})
        pip_args = run.call_args_list[1].args
        sync_args = run.call_args_list[2].args
        self.assertIn('--require-hashes', pip_args)
        self.assertIn('--only-binary', pip_args)
        self.assertIn('--no-build-isolation', sync_args)
        self.assertIn('--inexact', sync_args)
        self.assertIn('--frozen', sync_args)

    def test_configure_refuses_root_and_unknown_agents(self):
        with patch.object(acp.os, 'getuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'not root'):
                acp.configure([], ['--all'])
        with patch.object(acp.os, 'getuid', return_value=1000):
            with self.assertRaisesRegex(ValueError, 'Choose installed'):
                acp.configure([], ['nonexistent'])

    def test_native_install_retains_runtime_files(self):
        archive = self.root / 'agent.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for name, data, mode in [('bin/agent', b'#!/bin/sh\nexit 0\n', 0o755),
                                     ('lib/model.dat', b'required runtime', 0o644)]:
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(data), mode
                output.addfile(member, io.BytesIO(data))
        entry = {'id': 'native', 'label': 'Native', 'version': '1.0.0',
                 'distribution': {'binary': {'linux-x86_64': {
                     'archive': 'https://example.org/agent.tar.gz', 'cmd': './bin/agent',
                     'args': ['acp'], 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}}}}

        def copy_download(url, destination, expected):
            destination.write_bytes(archive.read_bytes())
            return expected

        with patch.object(acp, 'download', side_effect=copy_download):
            result = acp.install_agent(entry, 'linux-x86_64')
        self.assertEqual(result['status'], 'installed')
        self.assertEqual((acp.ROOT / 'native/lib/model.dat').read_text(), 'required runtime')
        subprocess.run(result['command'], check=True)

    def test_config_preserves_existing_settings_and_private_backup(self):
        home = self.root / 'home'
        home.mkdir()
        config = home / 'config.json'
        existing = {'version': 1, 'relay': {'enabled': True}, 'agents': {'providers': {
            'hermes': {'command': ['my-existing-hermes'], 'enabled': False}}}}
        config.write_text(json.dumps(existing))
        receipts = [{'id': 'hermes', 'status': 'installed', 'label': 'Hermes', 'command': ['new']},
                    {'id': 'gemini', 'status': 'installed', 'label': 'Gemini', 'command': ['gemini-acp']},
                    {'id': 'missing', 'status': 'unavailable'}]
        with patch.dict(os.environ, {'PASEO_HOME': str(home)}), patch.object(acp.os, 'getuid', return_value=1000):
            acp.configure(receipts, ['--all'])
            first = json.loads(config.read_text())
            acp.configure(receipts, ['--all'])
        self.assertEqual(json.loads(config.read_text()), first)
        self.assertEqual(first['relay'], existing['relay'])
        self.assertEqual(first['agents']['providers']['hermes'], existing['agents']['providers']['hermes'])
        self.assertNotIn('missing', first['agents']['providers'])
        self.assertEqual(first['agents']['providers']['gemini']['extends'], 'acp')
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        for backup in home.glob('config-before-acp-*.json'):
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_snapshot_has_all_paseo_entries_and_exact_package_versions(self):
        catalog = json.loads((Path(__file__).resolve().parents[1] / 'docker/acp-catalog.lock.json').read_text())
        ids = [entry['id'] for entry in catalog['agents']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('hermes', ids)
        for entry in catalog['agents']:
            dist = entry['distribution']
            self.assertTrue(dist or entry.get('unavailable'), entry['id'])
            if 'npx' in dist:
                self.assertRegex(dist['npx']['package'], r'@\d+\.\d+\.\d+$')
                self.assertTrue(dist['npx']['integrity'].startswith('sha512-'))
            for target in dist.get('binary', {}):
                self.assertIn(target, ('linux-aarch64', 'linux-x86_64'))

    def test_committed_dependency_locks_match_snapshot_hashes(self):
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / 'docker/acp-catalog.lock.json').read_text())
        packages = json.loads((root / 'docker/native-clis.lock.json').read_text())['packages']
        for agent in catalog['agents']:
            packages.extend(agent.get('npmPrerequisites', []))
            packages.extend(dist for key, dist in agent['distribution'].items() if key in ('npx', 'uvx'))
            if 'source' in agent['distribution']:
                packages.append({'lock': agent['distribution']['source']['buildLock']})
        with patch.object(acp, 'DEPS', root / 'docker/dependency-locks'):
            for dist in packages:
                data = acp.reviewed_lock(dist)
                self.assertTrue(data)
                if 'bin' in dist:
                    name = dist['package'].rsplit('@', 1)[0]
                    bins = json.loads(data)['packages'][f'node_modules/{name}']['bin']
                    self.assertIn(dist['bin'], bins, dist['package'])
                    acp.safe_path(self.root / 'package', bins[dist['bin']])


if __name__ == '__main__':
    unittest.main()
