export default function SectorTabs({ meta, filters, onChange }) {
  const sectors = [{ code: 'ALL', name: 'Group' }, ...(meta?.sectors || [])];
  return (
    <nav className="sector-tabs">
      {sectors.map((s) => (
        <button
          key={s.code}
          className={`tab ${filters.sector === s.code ? 'active' : ''}`}
          onClick={() => onChange({ sector: s.code })}
        >
          {s.code === 'ALL' ? 'Group' : `${s.code} ${s.name}`}
        </button>
      ))}
    </nav>
  );
}
