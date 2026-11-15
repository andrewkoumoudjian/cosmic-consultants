import type { Dataset, Objective, Rule, Runtime } from './engine.ts';

export type LoadProgress = { loadedFiles: number; totalFiles: number; loadedBytes: number; label: string };
export type LoadOptions = { initialObjectiveId?: string; onProgress?: (info: LoadProgress) => void };
type LoaderState = { base: string; manifest: { files: Record<string, string> }; monthlyCount: number; monthlyCols: Set<string>; pending: Map<string, Promise<void>> };
const loaders = new WeakMap<Dataset, LoaderState>();

export async function digest(bytes: ArrayBuffer): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function readStream(response: Response, onChunk: (n: number) => void): Promise<ArrayBuffer> {
  if (!response.body) {
    const buf = await response.arrayBuffer();
    onChunk(buf.byteLength);
    return buf;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      total += value.byteLength;
      onChunk(value.byteLength);
    }
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.byteLength;
  }
  return out.buffer;
}

export function usedMonthlyColumns(data: Dataset): string[] {
  const cols = new Set<string>();
  for (const r of data.rules) if (r.table === 'L1m' && r.earthColumn) cols.add(r.earthColumn);
  return [...cols];
}

export function monthlyColumnsForObjective(data: Dataset, objectiveId: string): string[] {
  const obj = data.objectives.find(o => o.objectiveId === objectiveId);
  const dims = obj ? new Set(obj.requiredDimensions) : null;
  const cols = new Set<string>();
  for (const r of data.rules as (Rule & { objectiveId?: string })[]) {
    if (r.table === 'L1m' && r.earthColumn && (!r.objectiveId || r.objectiveId === objectiveId) && (!dims || dims.has(r.dimension))) {
      cols.add(r.earthColumn);
    }
  }
  return [...cols];
}

async function fetchVerified(base: string, manifest: { files: Record<string, string> }, path: string, onChunk: (n: number) => void): Promise<ArrayBuffer> {
  if (!(path in manifest.files)) throw Error(`No recorded hash for ${path}.`);
  const response = await fetch(base + path);
  if (!response.ok) throw Error(`The planner data is unavailable (${path}). Publish the verified assembly with the documented release command, then reload.`);
  const bytes = await readStream(response, onChunk);
  if (await digest(bytes) !== manifest.files[path]) throw Error(`Data verification failed for ${path}.`);
  return bytes;
}

export async function ensureMonthly(data: Dataset, columns: string[], onProgress?: (info: LoadProgress) => void): Promise<void> {
  const state = loaders.get(data);
  if (!state) return;
  const wanted = [...new Set(columns)].filter(c => state.monthlyCols.has(c) && !(c in data.monthly));
  if (!wanted.length) return;
  let loadedFiles = 0, loadedBytes = 0;
  const totalFiles = wanted.length;
  const emit = (label: string) => onProgress?.({ loadedFiles, totalFiles, loadedBytes, label });
  for (const name of wanted) {
    let p = state.pending.get(name);
    if (!p) {
      p = (async () => {
        const b = await fetchVerified(state.base, state.manifest, `monthly/${name}.bin`, n => { loadedBytes += n; emit(name); });
        if (b.byteLength !== state.monthlyCount * 12 * 4) throw Error(`Incomplete monthly column ${name}.`);
        data.monthly[name] = new Float32Array(b);
      })().finally(() => state.pending.delete(name));
      state.pending.set(name, p);
    }
    await p;
    loadedFiles++;
    emit(name);
  }
}

export async function loadDataset(base = './data/planner-v1/', options: LoadOptions = {}): Promise<Dataset> {
  const onProgress = options.onProgress;
  let loadedFiles = 0, loadedBytes = 0, totalFiles = 7;
  const emit = (label: string) => onProgress?.({ loadedFiles, totalFiles, loadedBytes, label });
  const getManifest = async () => {
    const response = await fetch(base + 'build-manifest.json');
    if (!response.ok) throw Error('The planner data is unavailable (build-manifest.json). Publish the verified assembly with the documented release command, then reload.');
    const bytes = await readStream(response, n => { loadedBytes += n; emit('build-manifest.json'); });
    loadedFiles++;
    emit('build-manifest.json');
    return bytes;
  };
  const manifestBytes = await getManifest();
  const manifest = JSON.parse(new TextDecoder().decode(manifestBytes));
  if (manifest.synthetic !== false) throw Error('This planner requires the real published release.');
  const read = async (path: string) => {
    const b = await fetchVerified(base, manifest, path, n => { loadedBytes += n; emit(path); });
    loadedFiles++;
    emit(path);
    return b;
  };
  const json = async <T>(p: string): Promise<T> => JSON.parse(new TextDecoder().decode(await read(p))) as T;
  const objectives = await json<Objective[]>('objectives.json');
  const traitMap = await json<{ rules: Rule[] }>('trait-map.json');
  const monthlyMeta = await json<{ columns: Record<string, string> }>('monthly/monthly.json');
  const monthlyCols = new Set(Object.keys(monthlyMeta.columns));
  const initialCols: string[] = [];
  if (options.initialObjectiveId) {
    const obj = objectives.find(o => o.objectiveId === options.initialObjectiveId);
    const dims = obj ? new Set(obj.requiredDimensions) : null;
    for (const r of traitMap.rules as (Rule & { objectiveId?: string })[]) {
      if (r.table === 'L1m' && r.earthColumn && monthlyCols.has(r.earthColumn) && (!r.objectiveId || r.objectiveId === options.initialObjectiveId) && (!dims || dims.has(r.dimension))) {
        if (!initialCols.includes(r.earthColumn)) initialCols.push(r.earthColumn);
      }
    }
  } else {
    for (const r of traitMap.rules) if (r.table === 'L1m' && r.earthColumn && monthlyCols.has(r.earthColumn) && !initialCols.includes(r.earthColumn)) initialCols.push(r.earthColumn);
  }
  totalFiles = 7 + initialCols.length;
  emit('cells');
  const meta = await json<{ h3: string[]; count: number; dtype: string; columns: { name: string; offset: number; length: number }[] }>('cells.json');
  const runtime = await json<Runtime>('planner-runtime.json');
  const binary = await read('cells.bin');
  if (meta.dtype !== 'float32-le' || runtime.numericPolicy !== 'published-float32-no-epsilon') throw Error('Unsupported release numeric policy.');
  const yearly: Record<string, Float32Array> = {}, monthly: Record<string, Float32Array> = {};
  for (const c of meta.columns) {
    if (c.length !== meta.h3.length || c.offset < 0 || c.offset + 4 * c.length > binary.byteLength) throw Error('Invalid numeric layout.');
    yearly[c.name] = new Float32Array(binary, c.offset, c.length);
  }
  const dataset: Dataset = { h3: meta.h3, yearly, monthly, objectives, rules: traitMap.rules, runtime, inputs: manifest.inputs, manifestHash: await digest(manifestBytes) };
  loaders.set(dataset, { base, manifest, monthlyCount: meta.count, monthlyCols, pending: new Map() });
  await ensureMonthly(dataset, initialCols, p => onProgress?.({ loadedFiles: loadedFiles + p.loadedFiles, totalFiles, loadedBytes: loadedBytes + p.loadedBytes, label: p.label }));
  return dataset;
}


/** Load supplementary yearly measurements only when a consumer requests them. */
export async function ensureYearly(data: Dataset, columns: string[]): Promise<void> {
  const state = loaders.get(data);
  if (!state) return;
  for (const name of [...new Set(columns)]) {
    if (name in data.yearly) continue;
    if (!/^[a-z][a-z0-9_]*$/.test(name)) throw Error('Invalid yearly column name.');
    const key = `yearly/${name}.bin`;
    let pending = state.pending.get(key);
    if (!pending) {
      pending = (async () => {
        const bytes = await fetchVerified(state.base, state.manifest, key, () => {});
        if (bytes.byteLength !== data.h3.length * 4) throw Error(`Incomplete yearly column ${name}.`);
        data.yearly[name] = new Float32Array(bytes);
      })().finally(() => state.pending.delete(key));
      state.pending.set(key, pending);
    }
    await pending;
  }
}
