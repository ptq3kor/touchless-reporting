import { useFetch } from '../api.js';
import TrendArrow from './TrendArrow.jsx';
import Sparkline from './Sparkline.jsx';

const fmt = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));

export default function NwcSection({ filters }) {
  const { data, error } = useFetch('/api/nwc', filters);
  if (error) return <section className="card"><p className="muted">Failed to load NWC.</p></section>;
  if (!data) return <section className="card"><p className="muted">Loading…</p></section>;

  return (
    <section className="card">
      <h2>Net Working Capital</h2>
      <div className="kpi-row">
        {data.balances.map((b) => (
          <div className="kpi-card" key={b.measure}>
            <div className="kpi-label">{b.label}</div>
            <div className="kpi-value small-value">{fmt(b.value)} <span className="kpi-unit">€ m</span></div>
            <div className="kpi-trends"><TrendArrow pct={b.vs_py_pct} isCost={b.measure !== 'AP'} /></div>
            <Sparkline data={b.spark} favorable={b.measure === 'AP' ? (b.vs_py_pct ?? 0) >= 0 : (b.vs_py_pct ?? 0) <= 0} />
          </div>
        ))}
      </div>
      <div className="kpi-row">
        {data.flows.map((f) => (
          <div className="kpi-card" key={f.measure}>
            <div className="kpi-label">{f.label}</div>
            <div className="kpi-value small-value">{fmt(f.month)} <span className="kpi-unit">€ m</span></div>
            <div className="kpi-trends"><TrendArrow pct={f.vs_py_pct} isCost={f.is_cost} /></div>
            <div className="kpi-sub">YTD {fmt(f.ytd)} <TrendArrow pct={f.ytd_vs_py_pct} isCost={f.is_cost} suffix="" /></div>
            <Sparkline data={f.spark}
              favorable={f.is_cost ? (f.vs_py_pct ?? 0) <= 0 : (f.vs_py_pct ?? 0) >= 0} />
          </div>
        ))}
      </div>
    </section>
  );
}
