import { useState } from 'react';
import { useFetch } from './api.js';
import Header from './components/Header.jsx';
import SectorTabs from './components/SectorTabs.jsx';
import FilterBar from './components/FilterBar.jsx';
import SalesSection from './components/SalesSection.jsx';
import PnlSection from './components/PnlSection.jsx';
import SgaSection from './components/SgaSection.jsx';
import HeadcountSection from './components/HeadcountSection.jsx';
import NwcSection from './components/NwcSection.jsx';
import SummarySection from './components/SummarySection.jsx';

const DEFAULT_FILTERS = {
  year: 2024,
  month: 5,
  sector: 'ALL',
  area: null,
  subregion: null,
  country: null,
  entity_id: null,
  division: null,
  currency: 'EUR',
  view: 'NOM',
  cmp: 'CF',
};

export default function App() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const { data: meta } = useFetch('/api/meta/filters');

  // Cascading resets: changing a parent geography level clears its children.
  const update = (patch) => {
    setFilters((f) => {
      const next = { ...f, ...patch };
      if ('area' in patch) Object.assign(next, { subregion: null, country: null, entity_id: null });
      if ('subregion' in patch) Object.assign(next, { country: null, entity_id: null });
      if ('country' in patch) Object.assign(next, { entity_id: null });
      if ('sector' in patch) Object.assign(next, { division: null });
      if ('year' in patch && meta) {
        const months = meta.periods.months_by_year[String(patch.year)] || [];
        if (!months.includes(next.month)) next.month = months[months.length - 1] || 1;
      }
      return next;
    });
  };

  return (
    <div className="page">
      <Header meta={meta} filters={filters} onChange={update} />
      <SectorTabs meta={meta} filters={filters} onChange={update} />
      <FilterBar meta={meta} filters={filters} onChange={update} />
      <div className="grid">
        <div className="col-left">
          <SalesSection filters={filters} />
          <PnlSection filters={filters} />
          <SgaSection filters={filters} />
        </div>
        <div className="col-right">
          <HeadcountSection filters={filters} />
          <NwcSection filters={filters} />
          <SummarySection filters={filters} />
        </div>
      </div>
    </div>
  );
}
