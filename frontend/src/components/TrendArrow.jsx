// ▲/▼ colored by favorability: for cost measures a decrease is favorable.
export default function TrendArrow({ pct, isCost = false, suffix = 'vs PY', pp = false }) {
  if (pct === null || pct === undefined) return <span className="trend muted">—</span>;
  const up = pct >= 0;
  const favorable = isCost ? pct <= 0 : pct >= 0;
  const arrow = up ? '▲' : '▼';
  const sign = pct > 0 ? '+' : '';
  const unit = pp ? 'pp' : '%';
  return (
    <span className={`trend ${favorable ? 'pos' : 'neg'}`}>
      {arrow} {sign}{pct.toFixed(pp ? 2 : 1)}{unit} {suffix}
    </span>
  );
}
