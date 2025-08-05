import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { format, subDays } from 'date-fns'
import { metricsService } from '../services/api'

interface UsageData {
  date: string
  requests: number
  tokens: number
}

export function UsageAnalytics() {
  const [data, setData] = useState<UsageData[]>([])
  const [startDate, setStartDate] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'))
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchData()
  }, [startDate, endDate])

  const fetchData = async () => {
    setLoading(true)
    try {
      const response = await metricsService.usage(startDate, endDate)
      const aggregated = response.data.reduce((acc: any, item: any) => {
        const date = format(new Date(item.timestamp), 'yyyy-MM-dd')
        if (!acc[date]) {
          acc[date] = { date, requests: 0, tokens: 0 }
        }
        acc[date].requests++
        acc[date].tokens += item.tokens_used
        return acc
      }, {})
      setData(Object.values(aggregated))
    } catch (e) {
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ border: '1px solid #e0e0e0', borderRadius: 8, padding: 20 }}>
      <h2 style={{ margin: '0 0 20px' }}>Usage Analytics</h2>
      
      <div style={{ marginBottom: 20, display: 'flex', gap: 12 }}>
        <input
          type="date"
          value={startDate}
          onChange={e => setStartDate(e.target.value)}
          style={{ padding: 8, border: '1px solid #ddd', borderRadius: 4 }}
        />
        <input
          type="date"
          value={endDate}
          onChange={e => setEndDate(e.target.value)}
          style={{ padding: 8, border: '1px solid #ddd', borderRadius: 4 }}
        />
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>Loading...</div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis yAxisId="left" />
            <YAxis yAxisId="right" orientation="right" />
            <Tooltip />
            <Line yAxisId="left" type="monotone" dataKey="requests" stroke="#2196f3" name="Requests" />
            <Line yAxisId="right" type="monotone" dataKey="tokens" stroke="#4caf50" name="Tokens" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}