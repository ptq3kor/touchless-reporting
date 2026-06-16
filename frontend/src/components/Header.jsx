const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export default function Header({ meta, filters, onChange }) {
  const years = meta?.periods?.years || [2023, 2024];
  const months = meta?.periods?.months_by_year?.[String(filters.year)] || [];

  return (
    <header className="header">
      <div className="brand">
        <span className="bosch-wordmark">BOSCH</span>
        <span className="brand-divider" />
        <span className="brand-title">Management Dashboard</span>
      </div>
      <div className="header-controls">
        <select value={filters.year} onChange={(e) => onChange({ year: Number(e.target.value) })}>
          {years.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        <select value={filters.month} onChange={(e) => onChange({ month: Number(e.target.value) })}>
          {months.map((m) => (
            <option key={m} value={m}>{MONTH_NAMES[m - 1]}</option>
          ))}
        </select>
        <div className="toggle">
          {['CF', 'BP'].map((c) => (
            <button
              key={c}
              className={filters.cmp === c ? 'on' : ''}
              onClick={() => onChange({ cmp: c })}
            >
              vs {c}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
