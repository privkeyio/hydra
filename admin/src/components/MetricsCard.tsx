interface MetricsCardProps {
  title: string
  value: string | number
  trend?: number
  suffix?: string
}

export function MetricsCard({ title, value, trend, suffix = '' }: MetricsCardProps) {
  return (
    <div style={{ border: '1px solid #e0e0e0', borderRadius: 8, padding: 20 }}>
      <h3 style={{ margin: 0, fontSize: 14, color: '#666' }}>{title}</h3>
      <div style={{ fontSize: 28, fontWeight: 'bold', marginTop: 8 }}>
        {value}{suffix}
      </div>
      {trend !== undefined && (
        <div style={{ fontSize: 12, marginTop: 4, color: trend > 0 ? '#4caf50' : '#f44336' }}>
          {trend > 0 ? '+' : ''}{trend}%
        </div>
      )}
    </div>
  )
}