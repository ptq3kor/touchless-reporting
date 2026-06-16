function Select({ label, value, onChange, options, getKey, getLabel }) {
  return (
    <label className="filter-select">
      <span>{label}</span>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={getKey(o)} value={getKey(o)}>{getLabel(o)}</option>
        ))}
      </select>
    </label>
  );
}

export default function FilterBar({ meta, filters, onChange }) {
  if (!meta) return <div className="filter-bar" />;

  const subregions = meta.subregions.filter((s) => !filters.area || s.area === filters.area);
  const countries = meta.countries.filter(
    (c) =>
      (!filters.area || c.area === filters.area) &&
      (!filters.subregion || c.subregion === filters.subregion)
  );
  const countryCodes = new Set(countries.map((c) => c.code));
  const entities = meta.entities.filter(
    (e) => (!filters.country || e.country === filters.country) && countryCodes.has(e.country)
  );
  const divisions = meta.divisions.filter(
    (d) => filters.sector === 'ALL' || d.sector === filters.sector
  );

  return (
    <div className="filter-bar">
      <Select label="Area" value={filters.area} onChange={(v) => onChange({ area: v })}
        options={meta.areas} getKey={(a) => a} getLabel={(a) => a} />
      <Select label="Subregion" value={filters.subregion} onChange={(v) => onChange({ subregion: v })}
        options={subregions} getKey={(s) => s.name} getLabel={(s) => s.name} />
      <Select label="Country" value={filters.country} onChange={(v) => onChange({ country: v })}
        options={countries} getKey={(c) => c.code} getLabel={(c) => c.name} />
      <Select label="Entity" value={filters.entity_id}
        onChange={(v) => onChange({ entity_id: v ? Number(v) : null })}
        options={entities} getKey={(e) => e.id} getLabel={(e) => e.name} />
      <Select label="Division" value={filters.division} onChange={(v) => onChange({ division: v })}
        options={divisions} getKey={(d) => d.code} getLabel={(d) => `${d.code} ${d.name}`} />
      <div className="filter-toggles">
        <div className="toggle">
          {['EUR', 'LOCAL'].map((c) => (
            <button key={c} className={filters.currency === c ? 'on' : ''}
              onClick={() => onChange({ currency: c })}>
              {c === 'EUR' ? 'EUR' : 'Local'}
            </button>
          ))}
        </div>
        <div className="toggle">
          {['NOM', 'REAL'].map((v) => (
            <button key={v} className={filters.view === v ? 'on' : ''}
              onClick={() => onChange({ view: v })}>
              {v === 'NOM' ? 'Nominal' : 'Real (woc)'}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
