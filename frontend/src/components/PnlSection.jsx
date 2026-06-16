import { useFetch } from '../api.js';
import TrendArrow from './TrendArrow.jsx';

const fmt = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const fmt2 = (v) => (v === null || v === undefined ? '—' : v.toFixed(2));

export default function PnlSection({ filters }) {
  const { data, error } = useFetch('/api/pnl', filters);
  if (error) return <section className="card"><p className="muted">Failed to load P&L.</p></section>;
  if (!data) return <section className="card"><p className="muted">Loading…</p></section>;

  const e = data.ebit;
  return (
    <section className="card">
      <h2>P&L Highlights</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>EBIT (€ m)</th><th>ACT</th><th>PY</th><th>CF</th><th>BP</th>
            <th>vs PY</th><th>vs CF</th><th>vs BP</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Month</td>
            <td className="num strong">{fmt(e.month.act)}</td>
            <td className="num">{fmt(e.month.py)}</td>
            <td className="num">{fmt(e.month.cf)}</td>
            <td className="num">{fmt(e.month.bp)}</td>
            <td><TrendArrow pct={e.month.vs_py_pct} /></td>
            <td><TrendArrow pct={e.month.vs_cf_pct} suffix="" /></td>
            <td><TrendArrow pct={e.month.vs_bp_pct} suffix="" /></td>
          </tr>
          <tr>
            <td>YTD</td>
            <td className="num strong">{fmt(e.ytd.act)}</td>
            <td className="num">{fmt(e.ytd.py)}</td>
            <td className="num">{fmt(e.ytd.cf)}</td>
            <td className="num">{fmt(e.ytd.bp)}</td>
            <td><TrendArrow pct={e.ytd.vs_py_pct} /></td>
            <td><TrendArrow pct={e.ytd.vs_cf_pct} suffix="" /></td>
            <td><TrendArrow pct={e.ytd.vs_bp_pct} suffix="" /></td>
          </tr>
          <tr>
            <td>EBIT % of TNS</td>
            <td className="num strong">{fmt2(e.pct_of_tns.month_act)}%</td>
            <td className="num">{fmt2(e.pct_of_tns.month_py)}%</td>
            <td className="num">{fmt2(e.pct_of_tns.month_cf)}%</td>
            <td className="num">{fmt2(e.pct_of_tns.month_bp)}%</td>
            <td><TrendArrow pct={e.pct_of_tns.vs_py_pp} pp suffix="" /></td>
            <td><TrendArrow pct={e.pct_of_tns.vs_cf_pp} pp suffix="" /></td>
            <td><TrendArrow pct={e.pct_of_tns.vs_bp_pp} pp suffix="" /></td>
          </tr>
        </tbody>
      </table>
      <p className="muted small">
        YTD margin {fmt2(e.pct_of_tns.ytd_act)}% (PY {fmt2(e.pct_of_tns.ytd_py)}%)
      </p>
    </section>
  );
}
