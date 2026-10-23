"""Resolve complete, hashed Python graphs without running sdist build backends."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
catalog_path = ROOT / 'docker/acp-catalog.lock.json'
catalog = json.loads(catalog_path.read_text())
locks = ROOT / 'docker/dependency-locks'
for agent in catalog['agents']:
    dist = agent['distribution'].get('uvx')
    if not dist:
        continue
    output = locks / 'python' / f"{agent['id']}.txt"
    print(f"Locking Python {agent['id']}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        requirement = Path(tmp) / 'requirements.in'
        requirement.write_text(dist['package'] + '\n')
        subprocess.run(['uv', '--no-config', 'pip', 'compile', '--universal',
                        '--python-version', '3.12', '--only-binary', ':all:',
                        '--generate-hashes', '--no-header', '--no-annotate',
                        '--default-index', 'https://pypi.org/simple',
                        '--output-file', str(output), str(requirement)], check=True,
                       stdout=subprocess.DEVNULL)
    data = output.read_bytes()
    dist['lock'] = {'path': str(output.relative_to(locks)),
                    'sha256': hashlib.sha256(data).hexdigest()}
    catalog_path.write_text(json.dumps(catalog, indent=2) + '\n')

# Hermes' upstream build-system pins setuptools but leaves wheel unconstrained.
# Build the verified source with this separately locked backend graph instead.
build_output = locks / 'python/hermes-build.txt'
with tempfile.TemporaryDirectory() as tmp:
    requirement = Path(tmp) / 'backend.in'
    requirement.write_text('setuptools==83.0.0\nwheel==0.48.0\npackaging==26.0\n')
    subprocess.run(['uv', '--no-config', 'pip', 'compile', '--universal',
                    '--python-version', '3.14', '--only-binary', ':all:',
                    '--generate-hashes', '--no-header', '--no-annotate',
                    '--default-index', 'https://pypi.org/simple',
                    '--output-file', str(build_output), str(requirement)], check=True,
                   stdout=subprocess.DEVNULL)
source = next(agent for agent in catalog['agents'] if agent['id'] == 'hermes')['distribution']['source']
source['buildLock'] = {'path': 'python/hermes-build.txt',
                       'sha256': hashlib.sha256(build_output.read_bytes()).hexdigest()}
catalog_path.write_text(json.dumps(catalog, indent=2) + '\n')
