// Store only a request ID and a digest, never prompts or reference image bytes.
// Keep an unacknowledged submission across panel closes and page reloads.
export async function submitGenerationRequest<T>(
  endpoint: string,
  payload: unknown,
  send: (requestId: string) => Promise<T>,
): Promise<T> {
  const bytes = new TextEncoder().encode(JSON.stringify([endpoint, payload]));
  // FNV-1a is only a local lookup key, not a security check. The server compares
  // SHA-256 payload hashes and rejects collisions. This also works over LAN HTTP,
  // where SubtleCrypto and randomUUID are unavailable.
  let hash = 0xcbf29ce484222325n;
  for (const byte of bytes) hash = BigInt.asUintN(64, (hash ^ BigInt(byte)) * 0x100000001b3n);
  const fingerprint = `${bytes.length}:${hash.toString(16)}`;
  const storageKey = `generation-submission-v1:${fingerprint}`;
  let requestId = sessionStorage.getItem(storageKey);
  if (!requestId) {
    const random = crypto.getRandomValues(new Uint8Array(16));
    random[6] = (random[6] & 0x0f) | 0x40;
    random[8] = (random[8] & 0x3f) | 0x80;
    const hex = Array.from(random, byte => byte.toString(16).padStart(2, '0')).join('');
    requestId = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  // If browser storage is unavailable, fail before sending an untrackable POST.
  sessionStorage.setItem(storageKey, requestId);
  const result = await send(requestId);
  const record = result as { id?: unknown; generation_group_id?: unknown; jobs?: unknown } | null;
  const isBatch = endpoint.endsWith('/sets');
  const resultId = isBatch ? record?.generation_group_id : record?.id;
  if (typeof resultId !== 'string' || !resultId || (isBatch && !Array.isArray(record?.jobs))) {
    throw new Error('Generation response was incomplete; the original request ID has been retained.');
  }
  sessionStorage.removeItem(storageKey);
  return result;
}
