#!/usr/bin/python3
"""Install the reviewed ACP snapshot at build time; configure it as the service user."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen, Request
import zipfile

ROOT = Path('/opt/paseo-acp')
LOCK = Path('/usr/local/share/paseo-acp-catalog.json')
BIN = Path(os.environ.get('PASEO_ACP_BIN', '/usr/local/bin'))
DEPS = Path('/usr/local/share/paseo-dependency-locks')
NATIVE = Path('/usr/local/share/paseo-native-clis.json')
MAX_ARCHIVE_BYTES = 1024 ** 3
MAX_EXPANDED_BYTES = 2 * 1024 ** 3
MAX_FILES = 100000
TARGETS = {'amd64': 'linux-x86_64', 'arm64': 'linux-aarch64',
           'x86_64': 'linux-x86_64', 'aarch64': 'linux-aarch64'}


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def download(url, destination, expected=None):
    if not isinstance(expected, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
        raise ValueError('A reviewed SHA-256 is required before downloading a binary')
    if not url.startswith('https://'):
        raise ValueError(f'Only HTTPS downloads allowed: {url}')
    digest = hashlib.sha256()
    with urlopen(Request(url, headers={'User-Agent': 'paseo-agent-image'}), timeout=120) as response:
        if not response.url.startswith('https://'):
            raise ValueError('Download redirected away from HTTPS')
        with destination.open('wb') as output:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise ValueError('Archive download exceeds size limit')
                output.write(chunk)
                digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected.lower():
        raise ValueError(f'Checksum mismatch: {url}')
    return actual


def safe_path(directory, name):
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError(f'Archive path escapes installation: {name}')
    return path


def extract(archive, destination):
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            if len(source.infolist()) > MAX_FILES or sum(m.file_size for m in source.infolist()) > MAX_EXPANDED_BYTES:
                raise ValueError('Expanded archive exceeds limits')
            for member in source.infolist():
                path = safe_path(destination, member.filename)
                mode = member.external_attr >> 16
                if member.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                elif mode & 0o170000 == 0o120000:
                    target = source.read(member).decode()
                    safe_path(destination, str(path.parent.relative_to(destination) / target))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.symlink_to(target)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as incoming, path.open('wb') as output:
                        shutil.copyfileobj(incoming, output)
                    path.chmod(0o755 if mode & 0o111 else 0o644)
    else:
        with tarfile.open(archive) as source:
            members, size = [], 0
            for member in source:
                members.append(member)
                size += member.size
                if len(members) > MAX_FILES or size > MAX_EXPANDED_BYTES:
                    raise ValueError('Expanded archive exceeds limits')
            # Bookworm's Python 3.11 does not expose tarfile's data filter.
            # Extract only these explicitly validated types, never an unfiltered
            # extractall fallback. Strip special/write bits from every artifact.
            hardlinks = []
            for member in members:
                path = safe_path(destination, member.name)
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                    path.chmod(0o755)
                elif member.isfile():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with source.extractfile(member) as incoming, path.open('wb') as output:
                        shutil.copyfileobj(incoming, output)
                    path.chmod(0o755 if member.mode & 0o111 else 0o644)
                elif member.issym():
                    if Path(member.linkname).is_absolute():
                        raise ValueError('Absolute archive symlink rejected')
                    safe_path(destination, str(path.parent.relative_to(destination) / member.linkname))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.symlink_to(member.linkname)
                elif member.islnk():
                    if Path(member.linkname).is_absolute():
                        raise ValueError('Absolute archive hardlink rejected')
                    safe_path(destination, member.linkname)
                    hardlinks.append(member)
                else:
                    raise ValueError('Device, FIFO or unsupported tar entry rejected')
            for member in hardlinks:
                target = safe_path(destination, member.linkname)
                path = safe_path(destination, member.name)
                if not target.is_file():
                    raise ValueError('Archive hardlink must target an extracted regular file')
                path.parent.mkdir(parents=True, exist_ok=True)
                os.link(target, path, follow_symlinks=False)


def wrapper(name, command, env=None):
    if not re.fullmatch(r'[a-z][a-z0-9-]*', name):
        raise ValueError('Invalid wrapper name')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) for key in (env or {})):
        raise ValueError('Invalid environment variable name')
    path = BIN / name
    lines = ['#!/bin/sh', 'set -eu']
    lines += [f'if [ "${{{key}+x}}" != x ]; then export {key}={shlex.quote(value)}; fi'
              for key, value in (env or {}).items()]
    lines += ['exec ' + shlex.join([str(part) for part in command]) + ' "$@"', '']
    path.write_text('\n'.join(lines), encoding='utf-8')
    path.chmod(0o755)


def reviewed_lock(dist):
    reference = dist.get('lock', {})
    if not reference.get('path') or not reference.get('sha256'):
        raise ValueError('Missing reviewed dependency lock; regenerate locks before building')
    source = safe_path(DEPS, reference['path'])
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != reference['sha256']:
        raise ValueError('Dependency lock checksum mismatch')
    return data


def install_npm(dist, directory):
    data = reviewed_lock(dist)
    lock = json.loads(data)
    package, version = dist['package'].rsplit('@', 1)
    if lock['packages'][''].get('dependencies') != {package: version}:
        raise ValueError('Dependency lock does not match requested package')
    package_meta = lock['packages'][f'node_modules/{package}']
    if package_meta['integrity'] != dist['integrity']:
        raise ValueError(f"npm integrity differs from reviewed snapshot: {dist['package']}")
    # npm's .bin links can be missing even when the published executable was
    # installed (e.g. Cline 3.0.73). Resolve the entrypoint from reviewed package
    # metadata, not from npm's generated links or an unchecked fallback path.
    binaries = package_meta.get('bin', {})
    binary = binaries.get(dist['bin']) if isinstance(binaries, dict) else None
    if not isinstance(binary, str) or not binary:
        raise ValueError('Requested npm executable is absent from reviewed lock')
    package_root = safe_path(directory / 'node_modules', package)
    executable = safe_path(package_root, binary)
    for key, dependency in lock['packages'].items():
        if dependency.get('inBundle') and not dependency.get('resolved'):
            parent = key
            covered = False
            while '/node_modules/' in parent:
                parent = parent.rsplit('/node_modules/', 1)[0]
                owner = lock['packages'].get(parent, {})
                if (owner.get('integrity', '').startswith('sha512-') and
                        owner.get('resolved', '').startswith('https://registry.npmjs.org/')):
                    covered = True
                    break
            if covered:
                continue
        if key and (not dependency.get('integrity', '').startswith('sha512-') or
                    not dependency.get('resolved', '').startswith('https://registry.npmjs.org/')):
            raise ValueError('Unverified npm dependency in lock')
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'package-lock.json').write_bytes(data)
    (directory / 'package.json').write_text(json.dumps(lock['packages']['']))
    run('npm', 'ci', '--prefix', str(directory), '--no-audit', '--no-fund')
    # Recheck after lifecycle scripts: they must not redirect the entrypoint
    # outside the verified package or leave a non-executable placeholder.
    if package_root.resolve() != package_root:
        raise ValueError('Installed npm package directory was redirected')
    executable = safe_path(package_root, binary)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"Missing npm executable for {dist['package']}: {executable}")
    alias = BIN / dist['bin']
    if not alias.exists():
        alias.symlink_to(executable)
    return executable


def build_source(checkout, dist):
    # Frozen runtime locks do not pin PEP 517 build requirements. Preinstall a
    # separate, fully hashed backend graph, then disable implicit build installs.
    data = reviewed_lock({'lock': dist.get('buildLock', {})})
    requirements = checkout / 'build-requirements.lock'
    requirements.write_bytes(data)
    python = checkout / '.venv/bin/python'
    run('uv', 'venv', '--python', dist['python'], str(checkout / '.venv'))
    run('uv', 'pip', 'install', '--python', str(python), '--require-hashes',
        '--only-binary', ':all:', '-r', str(requirements))
    run('uv', 'sync', '--project', str(checkout), '--python', dist['python'],
        '--frozen', '--inexact', '--no-build-isolation', '--no-dev', '--extra', dist['extra'])


def install_agent(agent, target):
    entry = agent['distribution']
    if not re.fullmatch(r'[a-z][a-z0-9-]*', agent['id']):
        raise ValueError('Invalid agent ID')
    packages = list(agent.get('npmPrerequisites', []))
    packages += [entry[key] for key in ('npx', 'uvx') if key in entry]
    for package in packages:
        if not package.get('lock'):
            return {'id': agent['id'], 'status': 'unavailable', 'reason': 'Security: reviewed dependency lock missing'}
    binary = entry.get('source') or (entry.get('binary', {}).get(target) if not ('npx' in entry or 'uvx' in entry) else None)
    if binary and not re.fullmatch(r'[a-fA-F0-9]{64}', binary.get('sha256', '')):
        return {'id': agent['id'], 'status': 'unavailable', 'reason': 'Security: reviewed SHA-256 missing'}
    if 'source' in entry and not entry['source'].get('buildLock'):
        return {'id': agent['id'], 'status': 'unavailable', 'reason': 'Security: reviewed source build lock missing'}
    directory = ROOT / agent['id']
    directory.mkdir(parents=True, exist_ok=True)
    env = dict(agent.get('env', {}))
    digest = None
    for index, prerequisite in enumerate(agent.get('npmPrerequisites', [])):
        install_npm(prerequisite, directory / f'runtime-{index}')
    if 'installed' in entry:
        dist = entry['installed']
        executable = Path(dist['cmd'])
    elif 'npx' in entry:
        dist = entry['npx']
        # Each package has its own dependency graph and binaries, avoiding collisions.
        executable = install_npm(dist, directory)
    elif 'uvx' in entry:
        dist = entry['uvx']
        data = reviewed_lock(dist)
        requirements = directory / 'requirements.lock'
        requirements.write_bytes(data)
        run('uv', 'venv', '--python', '3.12', str(directory / 'venv'))
        run('uv', 'pip', 'install', '--python', str(directory / 'venv/bin/python'),
            '--require-hashes', '--only-binary', ':all:', '-r', str(requirements))
        executable = directory / 'venv/bin' / dist['cmd']
        if not (BIN / dist['cmd']).exists():
            (BIN / dist['cmd']).symlink_to(executable)
    else:
        dist = entry.get('source') or entry.get('binary', {}).get(target)
        if not dist:
            directory.rmdir()
            return {'id': agent['id'], 'status': 'unavailable',
                    'reason': agent.get('unavailable', f'No {target} distribution published')}
        with tempfile.TemporaryDirectory(prefix='paseo-acp-') as temporary:
            archive = Path(temporary) / 'download'
            digest = download(dist['archive'], archive, dist.get('sha256'))
            if dist.get('raw'):
                shutil.copyfile(archive, safe_path(directory, dist['cmd']))
            else:
                extract(archive, directory)
        if 'source' in entry:
            children = list(directory.iterdir())
            if len(children) != 1 or not children[0].is_dir():
                raise ValueError('Expected one source checkout directory')
            checkout = children[0]
            build_source(checkout, dist)
            directory = checkout
        executable = safe_path(directory, dist['cmd'])
        executable.chmod(executable.stat().st_mode | 0o755)
        alias_name = executable.name
        if not (BIN / alias_name).exists():
            (BIN / alias_name).symlink_to(executable)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"Missing executable for {agent['id']}: {executable}")
    env.update(dist.get('env', {}))
    command = [str(executable), *dist.get('args', [])]
    name = f"paseo-acp-{agent['id']}"
    wrapper(name, command, env)
    return {'id': agent['id'], 'status': 'installed', 'version': agent['version'],
            'label': agent['label'], 'command': [str(BIN / name)],
            'options': agent.get('options', {}), 'sha256': digest}


def install(catalog, arch, only=None):
    if os.geteuid() == 0:
        raise ValueError('Install agents in the unprivileged build stage')
    target = TARGETS[arch]
    ROOT.mkdir(parents=True, exist_ok=True)
    result = []
    selected = set(only.split(',')) if only else None
    if selected and selected - {a['id'] for a in catalog['agents']}:
        raise ValueError('Unknown agent in --only')
    for agent in catalog['agents']:
        if selected and agent['id'] not in selected:
            continue
        print(f"Installing ACP {agent['id']} {agent['version']} ({target})", flush=True)
        try:
            receipt = install_agent(agent, target)
        except Exception as error:
            raise RuntimeError(f"ACP installation failed for {agent['id']}: {error}") from error
        result.append(receipt)
        print(f"ACP {agent['id']}: {receipt['status']}", flush=True)
    (ROOT / 'installed.json').write_text(json.dumps(result, indent=2) + '\n')


def configure(receipts, selected):
    if os.getuid() == 0:
        raise ValueError('Run configure as paseo, not root')
    installed = {entry['id']: entry for entry in receipts if entry['status'] == 'installed'}
    ids = list(installed) if selected == ['--all'] else selected
    if not ids or set(ids) - installed.keys():
        raise ValueError('Choose installed agent IDs or --all; use paseo-acp list')
    home = Path(os.environ.get('PASEO_HOME', str(Path.home() / '.paseo')))
    home.mkdir(parents=True, exist_ok=True)
    path = home / 'config.json'
    if path.is_symlink():
        raise ValueError('Refusing to replace symlinked Paseo config')
    config = json.loads(path.read_text()) if path.exists() else {'version': 1}
    providers = config.setdefault('agents', {}).setdefault('providers', {})
    for id_ in ids:
        if id_ in providers:
            print(f'Keeping existing provider config: {id_}')
            continue
        entry = installed[id_]
        providers[id_] = {'extends': 'acp', 'label': entry['label'], 'command': entry['command']}
        if entry.get('options'):
            providers[id_]['options'] = entry['options']
    if path.exists():
        with tempfile.NamedTemporaryFile(prefix='config-before-acp-', suffix='.json', dir=home, delete=False) as backup:
            backup.write(path.read_bytes())
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=home, delete=False) as output:
        json.dump(config, output, indent=2)
        output.write('\n')
    os.replace(output.name, path)
    print('ACP providers saved. Run paseo reload, then authenticate each provider as paseo.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'install-native', 'list', 'configure', 'check'])
    parser.add_argument('ids', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--arch', default=platform.machine(), choices=list(TARGETS))
    parser.add_argument('--only', help='Build/debug subset of catalog IDs, comma separated')
    args = parser.parse_args()
    if args.action == 'install-native':
        if os.geteuid() == 0:
            raise ValueError('Install CLIs in the unprivileged build stage')
        for dist in json.loads(NATIVE.read_text())['packages']:
            install_npm(dist, ROOT / dist['id'])
        return
    if args.action == 'install':
        install(json.loads(LOCK.read_text()), args.arch, args.only)
        return
    receipts = json.loads((ROOT / 'installed.json').read_text())
    if args.action == 'configure':
        configure(receipts, ['--all'] if args.all else args.ids)
    else:
        for entry in receipts:
            if args.action == 'check' and entry['status'] == 'installed':
                executable = Path(entry['command'][0])
                if not executable.is_file() or not os.access(executable, os.X_OK):
                    raise ValueError(f"ACP wrapper missing: {entry['id']}")
                run('sh', '-n', str(executable))
            print(f"{entry['id']}: {entry['status']} {entry.get('version', entry.get('reason', ''))}")


if __name__ == '__main__':
    main()
