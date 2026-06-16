import { AreaChart, Area } from 'recharts';

export default function Sparkline({ data, favorable = true }) {
  if (!data || data.length === 0) return null;
  const color = favorable ? 'var(--pos-green)' : 'var(--neg-red)';
  return (
    <AreaChart width={60} height={28} data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
      <Area type="monotone" dataKey="value" stroke={color} fill={color}
        fillOpacity={0.15} strokeWidth={1.5} dot={false} isAnimationActive={false} />
    </AreaChart>
  );
}
