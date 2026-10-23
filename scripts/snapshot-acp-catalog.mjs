// Refresh deliberately, review the resulting lock file, then rebuild the image.
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

async function get(url, json = true) {
  const response = await fetch(url, { headers: { 'User-Agent': 'paseo-agent-image' }, signal: AbortSignal.timeout(60000) });
  if (!response.ok) throw new Error(`${response.status}: ${url}`);
  return json ? response.json() : response.text();
}

const commit = (await get('https://api.github.com/repos/getpaseo/paseo/commits/main')).sha;
const source = await get(`https://raw.githubusercontent.com/getpaseo/paseo/${commit}/packages/app/src/data/acp-provider-catalog.ts`, false);
const array = source.match(/const CATALOG_DATA = (\[[\s\S]*?\]) as const;/)?.[1];
if (!array) throw new Error('Paseo catalog format changed');
// Parse the data literal without evaluating downloaded JavaScript.
const entries = JSON.parse(array.replace(/"(?:\\.|[^"\\])*"|\b\w+(?=\s*:)|,(?=\s*[}\]])/g,
  token => token.startsWith('"') ? token : token === ',' ? '' : JSON.stringify(token)));
const registryUrl = 'https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json';
const registryText = await get(registryUrl, false);
const registry = JSON.parse(registryText);
const aliases = { grok: 'grok-build' };
const agents = entries.map(entry => {
  const registered = registry.agents.find(agent => agent.id === (aliases[entry.id] ?? entry.id));
  const distribution = registered ? structuredClone(registered.distribution) : {};
  if (distribution.binary) distribution.binary = Object.fromEntries(Object.entries(distribution.binary).filter(([key]) => key.startsWith('linux-')));
  return { id: entry.id, label: entry.title, version: registered?.version ?? entry.version,
    documentation: entry.installLink, env: entry.env ?? {}, options: entry.params ?? {}, distribution };
});
const find = id => agents.find(agent => agent.id === id);
find('codewhale').version = '0.10.1';
find('codewhale').distribution = { npx: { package: 'codewhale@0.10.1', args: ['serve', '--acp'] } };
// The retired Autohand adapter points users to the native ACP CLI instead.
find('autohand').version = '0.9.8';
find('autohand').distribution = { binary: {
  'linux-x86_64': { archive: 'https://github.com/autohandai/code-cli/releases/download/v0.9.8/autohand-linux-x64',
    raw: true, cmd: './autohand', args: ['--acp'], sha256: 'e58b4ef9076d960e56cbfc37267f0c0ecba14881ccdf9ff8ecc3360101bcb00d' },
  'linux-aarch64': { archive: 'https://github.com/autohandai/code-cli/releases/download/v0.9.8/autohand-linux-arm64',
    raw: true, cmd: './autohand', args: ['--acp'], sha256: 'd27bddb9729a2cd34cb9130bb8291d2a45ffa52472b6abf06782ca6c5ce63cf4' },
} };
const ampRuntime = await get('https://registry.npmjs.org/@ampcode/cli/latest');
find('amp-acp').npmPrerequisites = [{ package: `@ampcode/cli@${ampRuntime.version}`, bin: 'amp', integrity: ampRuntime.dist.integrity }];
find('hermes').version = 'v0.22.4';
find('hermes').distribution = { source: {
  archive: 'https://codeload.github.com/NousResearch/hermes-agent/tar.gz/4d04303818b61bf3aa09278af48356315515965b',
  sha256: '147a567a05402c2832ca12d7e0a33f48fc0e7f627018687cbae1f333dafff0c2',
  python: '3.14.9', args: ['acp'], cmd: '.venv/bin/hermes', extra: 'acp',
} };
const gjcRelease = await get('https://api.github.com/repos/Yeachan-Heo/gajae-code/releases/latest');
find('gjc').version = gjcRelease.tag_name;
find('gjc').distribution = { binary: Object.fromEntries(['x64', 'arm64'].map(arch => {
  const asset = gjcRelease.assets.find(asset => asset.name === `gjc-linux-${arch}`);
  if (!asset?.digest?.startsWith('sha256:')) throw new Error(`Missing GJC hash for ${arch}`);
  return [arch === 'x64' ? 'linux-x86_64' : 'linux-aarch64', {
    archive: asset.browser_download_url, sha256: asset.digest.slice(7), cmd: './gjc', args: ['acp'], raw: true,
  }];
})) };
const hopliteVersion = '3.0.0';
const hopliteBase = `https://hoplite.sh/downloads/releases/${hopliteVersion}`;
const hopliteHashes = await get(`${hopliteBase}/checksums.txt`, false);
find('hoplite').version = hopliteVersion;
find('hoplite').distribution = { binary: Object.fromEntries(['amd64', 'arm64'].map(arch => {
  const filename = `hoplite_${hopliteVersion}_linux_${arch}.tar.gz`;
  const hash = hopliteHashes.split('\n').find(line => line.trim().endsWith(` ${filename}`))?.split(/\s+/)[0];
  if (!hash) throw new Error(`Missing Hoplite hash for ${arch}`);
  return [arch === 'amd64' ? 'linux-x86_64' : 'linux-aarch64', {
    archive: `${hopliteBase}/${filename}`, sha256: hash, cmd: './hoplite', args: ['acp'],
  }];
})) };
const kiro = await get('https://prod.download.cli.kiro.dev/stable/latest/manifest.json');
find('kiro').version = kiro.version;
find('kiro').distribution = { binary: Object.fromEntries(['x86_64', 'aarch64'].map(arch => {
  const pkg = kiro.packages.find(pkg => pkg.targetTriple === `${arch}-unknown-linux-gnu` && pkg.fileType === 'tarGz');
  return [`linux-${arch}`, { archive: `https://prod.download.cli.kiro.dev/stable/${pkg.download}`,
    sha256: pkg.sha256, cmd: './kirocli/bin/kiro-cli', args: ['acp'] }];
})) };
find('traecli').unavailable = 'Official installer https://trae.cn/trae-cli/install_v2.sh returned HTTP 403 from the build-preparation environment; no verified redistributable archive available.';
// Copilot is already pinned and installed by the main Dockerfile.
agents.push({ id: 'copilot-acp', label: 'GitHub Copilot ACP', version: '1.0.102',
  documentation: 'https://paseo.sh/docs/supported-providers', env: {}, options: {},
  distribution: { installed: { cmd: '/opt/paseo-acp/bin/copilot', args: ['--acp'] } } });
for (const agent of agents) {
  if (agent.distribution.npx) {
    const spec = agent.distribution.npx.package;
    const split = spec.lastIndexOf('@');
    const name = spec.slice(0, split), version = spec.slice(split + 1);
    if (split <= 0 || !/^\d+\.\d+\.\d+/.test(version)) throw new Error(`Unpinned npm package: ${spec}`);
    const metadata = await get(`https://registry.npmjs.org/${name}/${version}`);
    const bins = typeof metadata.bin === 'string' ? { [name.split('/').at(-1)]: metadata.bin } : metadata.bin;
    const bin = Object.keys(bins ?? {}).find(bin => bin === name.split('/').at(-1)) ?? Object.keys(bins ?? {})[0];
    if (!bin || !metadata.dist.integrity) throw new Error(`No bin/integrity: ${spec}`);
    Object.assign(agent.distribution.npx, { bin, integrity: metadata.dist.integrity });
  }
  if (agent.distribution.uvx) {
    agent.distribution.uvx.package = agent.distribution.uvx.package.replace(/@(?=\d)/, '==');
    agent.distribution.uvx.cmd = agent.id === 'fast-agent' ? 'fast-agent-acp' : 'minion-code';
  }
  if (!Object.keys(agent.distribution).length && !agent.unavailable) throw new Error(`Missing distribution: ${agent.id}`);
}
const lock = { schemaVersion: 1, paseoCommit: commit, registryUrl,
  registrySha256: createHash('sha256').update(registryText).digest('hex'), agents };
// Keep already-reviewed locks/hashes only when their package/artifact is identical.
try {
  const previous = JSON.parse(await readFile(new URL('../docker/acp-catalog.lock.json', import.meta.url)));
  for (const agent of agents) {
    const old = previous.agents.find(entry => entry.id === agent.id);
    if (!old) continue;
    for (const type of ['npx', 'uvx']) {
      const before = old.distribution[type], after = agent.distribution[type];
      if (before?.package === after?.package && before?.lock &&
          (!after.integrity || before.integrity === after.integrity)) after.lock = before.lock;
    }
    for (const dist of agent.npmPrerequisites ?? []) {
      const before = old.npmPrerequisites?.find(p => p.package === dist.package && p.integrity === dist.integrity);
      if (before?.lock) dist.lock = before.lock;
    }
    for (const [target, dist] of Object.entries(agent.distribution.binary ?? {})) {
      const before = old.distribution.binary?.[target];
      if (!dist.sha256 && before?.archive === dist.archive && before?.sha256) dist.sha256 = before.sha256;
    }
    if (agent.distribution.source?.archive === old.distribution.source?.archive && old.distribution.source?.buildLock) {
      agent.distribution.source.buildLock = old.distribution.source.buildLock;
    }
  }
} catch (error) { if (error.code !== 'ENOENT') throw error; }
await writeFile(new URL('../docker/acp-catalog.lock.json', import.meta.url), JSON.stringify(lock, null, 2) + '\n');
console.log(`Pinned ${agents.length} ACP catalog entries from Paseo ${commit}`);
