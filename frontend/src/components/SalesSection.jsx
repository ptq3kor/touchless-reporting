import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from 'recharts';
import { useFetch } from '../api.js';
import KpiCard from './KpiCard.jsx';

const LABELS = { TGS: 'TGS', TNS: 'TNS', INT_SALES: 'Int. Sales', STP_REGION: 'STP Region' };

export default function SalesSection({ filters }) {
  const { data, error } = useFetch('/api/sales', filters);
  if (error) return <section className="card"><p className="muted">Failed to load sales.</p></section>;
  if (!data) return <section className="card"><p className="muted">Loading…</p></section>;

  const note = data.meta.currency_note;
  const unit = data.meta.currency_used === 'LOCAL' ? `${data.meta.local_currency} m` : '€ m';

  return (
    <section className="card">
      <h2>Sales Performance</h2>
      {note && <p className="notice">{note}</p>}
      <div className="kpi-row">
        {data.kpis.map((k) => (
          <KpiCard key={k.measure} label={LABELS[k.measure] || k.label} kpi={k}
            cmp={data.meta.cmp} unit={unit} />
        ))}
      </div>
      <div className="chart-block">
        <h3>TNS by Business Sector</h3>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={data.sector_breakdown} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="sector" tickLine={false} fontSize={12} />
            <YAxis tickLine={false} fontSize={11} width={48} />
            <Tooltip
              formatter={(v, _n, p) => [`€ ${v.toLocaleString()}m (${p.payload.vs_py_pct > 0 ? '+' : ''}${p.payload.vs_py_pct}% vs PY)`, p.payload.name]}
            />
            <Bar dataKey="tns" isAnimationActive={false}>
              {data.sector_breakdown.map((b) => (
                <Cell key={b.sector}
                  fill={filters.sector === b.sector ? 'var(--bosch-darkblue)' : 'var(--bosch-blue)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
