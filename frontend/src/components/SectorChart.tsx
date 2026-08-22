import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'

interface SectorChartProps {
  data: Record<string, number>;
}


const SECTOR_LABELS: Record<string, string> = {
  water:       'Water',
  roads:       'Roads',
  sanitation:  'Sanitation',
  health:      'Health',
  education:   'Education',
  electricity: 'Electricity',
  other:       'Other',
}

// Resolve CSS variable to a fallback hex (recharts needs concrete colors)
const COLORS_HEX: Record<string, string> = {
  water:       '#38bdf8',
  roads:       '#a78bfa',
  sanitation:  '#34d399',
  health:      '#fb7185',
  education:   '#fbbf24',
  electricity: '#60a5fa',
  other:       '#94a3b8',
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ name: string; value: number; payload: { sector: string } }>;
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  return (
    <div className="custom-tooltip">
      <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
        {SECTOR_LABELS[item.payload.sector] ?? item.payload.sector}
      </div>
      <div style={{ color: 'var(--text-secondary)' }}>{item.value} reports</div>
    </div>
  )
}

export default function SectorChart({ data }: SectorChartProps) {
  const chartData = Object.entries(data).map(([sector, count]) => ({
    sector,
    name: SECTOR_LABELS[sector] ?? sector,
    value: count,
  }))

  if (!chartData.length) {
    return (
      <div className="empty-state" style={{ height: 220 }}>
        <span>No sector data yet</span>
      </div>
    )
  }

  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={90}
            paddingAngle={3}
            dataKey="value"
            strokeWidth={0}
          >
            {chartData.map((entry) => (
              <Cell
                key={entry.sector}
                fill={COLORS_HEX[entry.sector] ?? COLORS_HEX.other}
              />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(value: string) => (
              <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{value}</span>
            )}
            iconSize={8}
            iconType="circle"
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
