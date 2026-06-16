import { useFetch } from '../api.js';
import TrendArrow from './TrendArrow.jsx';

const fmt = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const GROUP_TITLES = { FIXED: 'Fixed', VARIABLE: 'Variable', OTHER: 'Other Op Inc/Exp' };

export default function SgaSection({ filters }) {
  const { data, error } = useFetch('/api/sga', filters);
  if (error) return <section className="card"><p className="muted">Failed to load SG&A.</p></section>;
  if (!data) return <section className="card"><p className="muted">Loading…</p></section>;

  let lastGroup = null;
  return (
    <section className="card">
      <h2>SG&A Cost Breakdown</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th></th><th>Month</th><th>YTD</th><th>YTD PY</th>
            <th>vs PY</th><th>vs {data.meta.cmp}</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => {
            const header = r.group !== lastGroup ? (
              <tr key={`g-${r.group}`} className="group-row">
                <td colSpan={6}>{GROUP_TITLES[r.group] || r.group}</td>
              </tr>
            ) : null;
            lastGroup = r.group;
            return [
              header,
              <tr key={r.measure}>
                <td>{r.label}</td>
                <td className="num">{fmt(r.month.value)}</td>
                <td className="num strong">{fmt(r.ytd.value)}</td>
                <td className="num">{fmt(r.ytd.py)}</td>
                <td><TrendArrow pct={r.ytd.vs_py_pct} isCost={r.is_cost} suffix="" /></td>
                <td><TrendArrow pct={r.ytd.vs_cmp_pct} isCost={r.is_cost} suffix="" /></td>
              </tr>,
            ];
          })}
          <tr className="total-row">
            <td>SG&A total (Fixed + Variable) YTD</td>
            <td></td>
            <td className="num strong">{fmt(data.totals.sga_total_ytd)}</td>
            <td></td>
            <td><TrendArrow pct={data.totals.vs_py_pct} isCost suffix="" /></td>
            <td></td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}
