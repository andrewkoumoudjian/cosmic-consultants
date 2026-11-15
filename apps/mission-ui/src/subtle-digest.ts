/**
 * Browsers only expose crypto.subtle on HTTPS or localhost. Opened over plain HTTP (for example a Tailscale
 * address), the data loader's SHA-256 check would crash. This fills in digest('SHA-256') with @noble/hashes,
 * so every file is still verified against the manifest; nothing is skipped.
 */
import { sha256 } from '@noble/hashes/sha2.js';

const c = globalThis.crypto as Crypto & { subtle?: SubtleCrypto };
if (c && !c.subtle) {
  const digest = async (algorithm: AlgorithmIdentifier, data: BufferSource): Promise<ArrayBuffer> => {
    const name = typeof algorithm === 'string' ? algorithm : algorithm.name;
    if (name.toUpperCase() !== 'SHA-256') throw new Error(`digest: only SHA-256 is available here, not ${name}`);
    const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    const out = sha256(bytes);
    return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength) as ArrayBuffer;
  };
  Object.defineProperty(c, 'subtle', { value: { digest } as unknown as SubtleCrypto, configurable: true });
}
