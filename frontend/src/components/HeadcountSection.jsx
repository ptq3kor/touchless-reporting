import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { useFetch } from '../api.js';
import TrendArrow from './TrendArrow.jsx';

const fmtI = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('en-US'));

export default function HeadcountSection({ filters }) {
  const { data, error } = useFetch('/api/headcount', filters);
  if (error) return <section className="card"><p className="muted">Failed to load headcount.</p></section>;
  if (!data) return <section className="card"><p className="muted">Loading…</p></section>;

  const c = data.cards;
  return (
    <section className="card">
      <h2>Headcount &amp; Personnel</h2>
      <div className="kpi-row">
        <div className="kpi-card">
          <div className="kpi-label">Total HC (state)</div>
          <div className="kpi-value">{fmtI(c.state.total)}</div>
          <div className="kpi-trends"><TrendArrow pct={c.state.vs_py_pct} isCost /></div>
          <div className="kpi-sub">Direct {c.state.direct_pct ?? '—'}% · Avg {fmtI(c.avg.total)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">PC (FTE)</div>
          <div className="kpi-value">{fmtI(c.pc_fte.total)}</div>
          <div className="kpi-trends">
            <TrendArrow pct={c.pc_fte.vs_py_pct} isCost />
            <TrendArrow pct={c.pc_fte.vs_cmp_pct} isCost suffix={`vs ${data.meta.cmp}`} />
          </div>
          <div className="kpi-sub">Direct {c.pc_fte.direct_pct ?? '—'}%</div>
        </div>
      </div>
      <div className="chart-block">
        <h3>12-Month Trend</h3>
        <ResponsiveContainer width="100%" height={160}>
          <ComposedChart data={data.trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="label" fontSize={10} tickLine={false} interval={1} />
            <YAxis fontSize={10} width={56} tickLine={false}
              domain={['auto', 'auto']} tickFormatter={(v) => v.toLocaleString()} />
            <Tooltip formatter={(v) => v.toLocaleString()} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="hc_state" name="HC state" fill="var(--bosch-blue)" isAnimationActive={false} />
            <Line dataKey="pc_fte" name="PC FTE" stroke="var(--bosch-darkblue)"
              strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
