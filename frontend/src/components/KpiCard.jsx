import TrendArrow from './TrendArrow.jsx';

const fmt = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));

export default function KpiCard({ label, kpi, cmp, isCost = false, unit = '€ m' }) {
  const showReal = kpi.real_nominal && kpi.real_nominal.real !== null
    && kpi.real_nominal.nom !== kpi.real_nominal.real;
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {fmt(kpi.month.value)} <span className="kpi-unit">{unit}</span>
      </div>
      <div className="kpi-trends">
        <TrendArrow pct={kpi.month.vs_py_pct} isCost={isCost} />
        <TrendArrow pct={kpi.month.vs_cmp_pct} isCost={isCost} suffix={`vs ${cmp}`} />
      </div>
      <div className="kpi-sub">
        YTD {fmt(kpi.ytd.value)} <TrendArrow pct={kpi.ytd.vs_py_pct} isCost={isCost} />
      </div>
      {showReal && (
        <div className="kpi-foot">
          Nominal {fmt(kpi.real_nominal.nom)} · Real (woc) {fmt(kpi.real_nominal.real)}
        </div>
      )}
    </div>
  );
}
