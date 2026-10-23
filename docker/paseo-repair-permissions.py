#!/usr/bin/python3
"""Repair verified inodes in the service home, without following links or mounts."""
import os
from pathlib import Path
import stat
import sys

FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


def warn(message):
    print(f'paseo-permissions: warning: {message}', file=sys.stderr)


def mount_id(fd):
    # st_dev alone cannot identify bind mounts of the same filesystem.
    with open(f'/proc/self/fdinfo/{fd}', encoding='ascii') as info:
        for line in info:
            if line.startswith('mnt_id:'):
                return int(line.split(':', 1)[1])
    raise OSError('cannot verify mount identity')


def open_directory(path):
    fd = os.open('/', FLAGS | os.O_DIRECTORY)
    try:
        for part in Path(os.path.abspath(path)).parts[1:]:
            child = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


class Repair:
    def __init__(self, home, env):
        self.home = Path(os.path.abspath(home))
        self.private_dirs = set()
        self.private_files = {'.claude.json'}
        self.parents = {''}
        self.gh = None
        codex = self.relative(env.get('CODEX_HOME', str(self.home / '.codex')))
        claude = self.relative(env.get('CLAUDE_CONFIG_DIR', str(self.home / '.claude')))
        xdg = env.get('XDG_CONFIG_HOME', str(self.home / '.config'))
        gh = self.relative(env.get('GH_CONFIG_DIR', str(Path(xdg) / 'gh')))
        if codex is not None:
            self.private_dirs.update([codex, f'{codex}/tmp'])
            self.private_files.add(f'{codex}/config.toml')
        if claude is not None:
            self.private_dirs.add(claude)
        if gh is not None:
            self.gh = gh
        for name in [codex, claude, gh, self.relative(xdg)]:
            if name is not None:
                self.parents.update(str(p) if str(p) != '.' else '' for p in Path(name).parents)

    def relative(self, path):
        # Never resolve links here: that would authorize an external link target.
        try:
            relative = Path(os.path.abspath(path)).relative_to(self.home)
        except ValueError:
            warn(f'config path outside authorized home skipped: {path}')
            return None
        if not relative.parts:
            warn('config directory cannot be the entire home')
            return None
        return str(relative)

    def visit(self, fd, relative, device, mount):
        current = os.fstat(fd)
        if current.st_dev != device or mount_id(fd) != mount:
            return
        directory = stat.S_ISDIR(current.st_mode)
        if not directory and (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1):
            return  # Hardlinks might alias protected files outside the home.
        if os.geteuid() == 0 and (current.st_uid, current.st_gid) != (1000, 1000):
            os.fchown(fd, 1000, 1000)
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        in_gh = self.gh is not None and (relative == self.gh or relative.startswith(self.gh + '/'))
        if directory:
            if relative == '' or relative in self.private_dirs or in_gh:
                os.fchmod(fd, 0o700)
            elif relative in self.parents:
                os.fchmod(fd, mode | 0o700)
            for name in os.listdir(fd):
                child = None
                try:
                    expected = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if not (stat.S_ISDIR(expected.st_mode) or stat.S_ISREG(expected.st_mode)):
                        continue
                    flags = FLAGS | (os.O_DIRECTORY if stat.S_ISDIR(expected.st_mode) else 0)
                    child = os.open(name, flags, dir_fd=fd)
                    actual = os.fstat(child)
                    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                        continue
                    self.visit(child, f'{relative}/{name}' if relative else name, device, mount)
                except (FileNotFoundError, NotADirectoryError):
                    continue
                except OSError as error:
                    warn(f'skipped entry {name!r}: {error.strerror}')
                finally:
                    if child is not None:
                        os.close(child)
        elif relative in self.private_files or in_gh:
            os.fchmod(fd, 0o600)

    def run(self):
        fd = open_directory(self.home)
        try:
            self.visit(fd, '', os.fstat(fd).st_dev, mount_id(fd))
        finally:
            os.close(fd)


if __name__ == '__main__':
    Repair(sys.argv[1], os.environ).run()
