import { useState } from 'react';
import { useFetch, streamSSE } from '../api.js';
import Assistant from './Assistant.jsx';

export default function SummarySection({ filters }) {
  const { data, error } = useFetch('/api/summary', filters);
  const [aiText, setAiText] = useState('');
  const [aiError, setAiError] = useState(null);
  const [generating, setGenerating] = useState(false);

  const generate = async () => {
    setAiText('');
    setAiError(null);
    setGenerating(true);
    try {
      await streamSSE('/api/assistant/generate-summary', { filters }, {
        onDelta: (d) => setAiText((t) => t + d),
        onError: (e) => setAiError(e),
        onDone: () => setGenerating(false),
      });
    } catch (e) {
      setAiError(String(e));
    } finally {
      setGenerating(false);
    }
  };

  if (error) return <section className="card"><p className="muted">Failed to load summary.</p></section>;
  if (!data) return <section className="card"><p className="muted">Loading…</p></section>;

  const mbr = data.mbr_status || {};
  return (
    <section className="card">
      <h2>Executive Summary</h2>
      <div className="badges">
        {['APPROVED', 'SUBMITTED', 'DRAFT'].map((s) =>
          mbr[s] ? <span key={s} className={`badge mbr-${s.toLowerCase()}`}>{mbr[s]} {s.toLowerCase()}</span> : null
        )}
        {data.anomalies.map((a, i) => (
          <span key={i} className={`badge sev-${a.severity.toLowerCase()}`} title={`${a.entity || ''}: ${a.message}`}>
            {a.severity} {a.rule}
          </span>
        ))}
      </div>
      <ul className="bullets">
        {data.bullets.map((b, i) => <li key={i}>{b}</li>)}
      </ul>
      <div className="ai-summary">
        <button className="btn-primary" onClick={generate} disabled={generating}>
          {generating ? 'Generating…' : 'Generate executive summary'}
        </button>
        {aiError && <p className="notice">{aiError}</p>}
        {aiText && <div className="ai-summary-text">{aiText}</div>}
      </div>
      <Assistant filters={filters} />
    </section>
  );
}
