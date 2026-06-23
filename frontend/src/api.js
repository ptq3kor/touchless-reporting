import { useEffect, useState } from 'react';

// In production (BTP), API_BASE points to the backend app URL.
// In local dev, it's empty (Vite proxy handles /api -> localhost:8000).
const API_BASE = import.meta.env.VITE_API_BASE || '';

export function toQuery(filters) {
  const params = new URLSearchParams();
  Object.entries(filters || {}).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '' && v !== 'ALL_NONE') params.set(k, v);
  });
  return params.toString();
}

export function useFetch(path, filters) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const qs = filters ? toQuery(filters) : '';

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(qs ? `${API_BASE}${path}?${qs}` : `${API_BASE}${path}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [path, qs]);

  return { data, error, loading };
}

// POST to an SSE endpoint and feed deltas to callbacks.
export async function streamSSE(path, body, { onDelta, onError, onDone }) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split('\n\n');
    buf = events.pop();
    for (const ev of events) {
      const line = ev.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.delta) onDelta?.(payload.delta);
      else if (payload.error) onError?.(payload.error);
      else if (payload.done) onDone?.();
    }
  }
  onDone?.();
}
