// Resolve metadata only. Never execute downloaded package scripts while locking.
import { readFile, writeFile, mkdir, mkdtemp } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';

const exec = promisify(execFile);
const root = new URL('../', import.meta.url);
const catalogPath = new URL('docker/acp-catalog.lock.json', root);
const catalog = JSON.parse(await readFile(catalogPath));
const locks = new URL('docker/dependency-locks/', root);
await mkdir(new URL('npm/', locks), { recursive: true });
await mkdir(new URL('python/', locks), { recursive: true });
const npmCli = join(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js');
const hash = data => createHash('sha256').update(data).digest('hex');
async function get(url) {
  const response = await fetch(url, { headers: { 'User-Agent': 'paseo-agent-image' }, signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.json();
}
const nativeSpecs = ['@openai/codex@0.163.0', '@anthropic-ai/claude-code@2.1.306',
  '@github/copilot@1.0.102', '@opencode/cli@2.1.2', '@earendil-works/pi-coding-agent@1.4.0'];
const native = [];
for (const spec of nativeSpecs) {
  const split = spec.lastIndexOf('@');
  const meta = await get(`https://registry.npmjs.org/${spec.slice(0, split)}/${spec.slice(split + 1)}`);
  const bin = Object.keys(meta.bin)[0];
  native.push({ id: `native-${bin}`, package: spec, bin, integrity: meta.dist.integrity });
}

async function freeze(id, dist) {
  const path = `npm/${id}.json`;
  if (dist.lock) {
    try {
      const bytes = await readFile(new URL(dist.lock.path, locks));
      if (hash(bytes) === dist.lock.sha256) return;
    } catch {}
  }
  const split = dist.package.lastIndexOf('@');
  const name = dist.package.slice(0, split), version = dist.package.slice(split + 1);
  const temporary = await mkdtemp(join(tmpdir(), 'paseo-lock-'));
  await writeFile(join(temporary, 'package.json'), JSON.stringify({
    name: `paseo-${id}`, version: '1.0.0', private: true, dependencies: { [name]: version },
  }));
  await writeFile(join(temporary, '.npmrc'), 'registry=https://registry.npmjs.org/\n');
  console.log(`Locking ${id}: ${dist.package}`);
  await exec(process.execPath, [npmCli, 'install', '--prefix', temporary, '--package-lock-only',
    '--ignore-scripts', '--no-audit', '--no-fund', '--loglevel=error',
    '--userconfig', join(temporary, '.npmrc'), '--registry=https://registry.npmjs.org/'],
    { timeout: 300000, maxBuffer: 1024 * 1024 });
  const bytes = await readFile(join(temporary, 'package-lock.json'));
  const lock = JSON.parse(bytes);
  if (lock.packages[`node_modules/${name}`]?.integrity !== dist.integrity) throw new Error(`Top-level integrity changed: ${id}`);
  for (const [key, pkg] of Object.entries(lock.packages)) {
    if (pkg.inBundle && !pkg.resolved) {
      let parent = key;
      let covered = false;
      while (parent.includes('/node_modules/')) {
        parent = parent.slice(0, parent.lastIndexOf('/node_modules/'));
        const owner = lock.packages[parent];
        if (owner?.integrity?.startsWith('sha512-') && owner.resolved?.startsWith('https://registry.npmjs.org/')) { covered = true; break; }
      }
      if (covered) continue;
    }
    if (key && (!pkg.integrity?.startsWith('sha512-') || !pkg.resolved?.startsWith('https://registry.npmjs.org/'))) {
      throw new Error(`Unverified non-registry dependency in ${id}: ${key}`);
    }
  }
  await writeFile(new URL(path, locks), bytes);
  dist.lock = { path, sha256: hash(bytes) };
  delete dist.lockError;
}

const nativePath = new URL('docker/native-clis.lock.json', root);
let existing = [];
try { existing = JSON.parse(await readFile(nativePath)).packages; } catch {}
for (const dist of native) {
  const previous = existing.find(p => p.package === dist.package);
  if (previous?.lock) dist.lock = previous.lock;
  await freeze(dist.id, dist);
  await writeFile(nativePath, JSON.stringify({ packages: native }, null, 2) + '\n');
}
for (const agent of catalog.agents) {
  for (const [index, dist] of (agent.npmPrerequisites ?? []).entries()) {
    try { await freeze(`${agent.id}-runtime-${index}`, dist); }
    catch (error) { dist.lockError = error.message; console.error(error.message); }
  }
  if (agent.distribution.npx) {
    try { await freeze(agent.id, agent.distribution.npx); }
    catch (error) { agent.distribution.npx.lockError = error.message; console.error(error.message); }
  }
  // Use published GitHub asset digests; never manufacture a trusted hash in a build.
  const releases = new Map();
  for (const dist of Object.values(agent.distribution.binary ?? {})) {
    if (dist.sha256) continue;
    const match = dist.archive.match(/^https:\/\/github.com\/([^/]+\/[^/]+)\/releases\/download\/([^/]+)\/(.+)$/);
    if (match) {
      try {
        const url = `https://api.github.com/repos/${match[1]}/releases/tags/${match[2]}`;
        if (!releases.has(url)) releases.set(url, await get(url));
        const asset = releases.get(url).assets.find(a => a.name === decodeURIComponent(match[3]));
        if (asset?.digest?.startsWith('sha256:')) dist.sha256 = asset.digest.slice(7);
      } catch (error) { console.error(error.message); }
    }
  }
  await writeFile(catalogPath, JSON.stringify(catalog, null, 2) + '\n');
}
const uv = await get('https://pypi.org/pypi/uv/0.13.5/json');
const wheels = uv.urls.filter(file => file.packagetype === 'bdist_wheel');
await writeFile(new URL('python/uv.txt', locks), `uv==0.13.5 \\\n${wheels.map((file, i) => `    --hash=sha256:${file.digests.sha256}${i < wheels.length - 1 ? ' \\' : ''}`).join('\n')}\n`);
console.log('Dependency metadata and binary digests saved. Review all lock diffs.');
