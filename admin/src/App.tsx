import { useState, useEffect } from 'react'
import { MetricsCard } from './components/MetricsCard'
import { TaskQueue } from './components/TaskQueue'
import { APIKeyManager } from './components/APIKeyManager'
import { UsageAnalytics } from './components/UsageAnalytics'
import { useWebSocket } from './hooks/useWebSocket'
import { metricsService, taskService, apiKeyService } from './services/api'
import { exportUsageToCSV } from './utils/export'
import { format, subDays } from 'date-fns'
import type { Metrics, Task, APIKey } from './types'

export function App() {
  const [metrics, setMetrics] = useState<Metrics>({
    request_count: 0,
    error_rate: 0,
    avg_latency: 0,
    active_tasks: 0,
    queue_size: 0
  })
  const [tasks, setTasks] = useState<Task[]>([])
  const [apiKeys, setApiKeys] = useState<APIKey[]>([])
  const ws = useWebSocket('ws://localhost:8000/ws/admin')

  useEffect(() => {
    fetchInitialData()
    
    if (ws) {
      const unsubMetrics = ws.subscribe('metrics', (data) => {
        setMetrics(data.metrics)
      })
      
      const unsubTask = ws.subscribe('task_update', (data) => {
        setTasks(prev => {
          const index = prev.findIndex(t => t.id === data.task.id)
          if (index >= 0) {
            const updated = [...prev]
            updated[index] = data.task
            return updated
          }
          return [data.task, ...prev].slice(0, 50)
        })
      })

      return () => {
        unsubMetrics()
        unsubTask()
      }
    }
  }, [ws])

  const fetchInitialData = async () => {
    try {
      const [metricsRes, tasksRes, keysRes] = await Promise.all([
        metricsService.realtime(),
        taskService.queue(),
        apiKeyService.list()
      ])
      setMetrics(metricsRes.data)
      setTasks(tasksRes.data)
      setApiKeys(keysRes.data)
    } catch (e) {}
  }

  const handleExport = async () => {
    const startDate = format(subDays(new Date(), 30), 'yyyy-MM-dd')
    const endDate = format(new Date(), 'yyyy-MM-dd')
    try {
      await exportUsageToCSV(startDate, endDate)
    } catch (e) {
      alert('Export failed')
    }
  }

  return (
    <div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Hydra Admin Dashboard</h1>
        <button onClick={handleExport} style={{
          padding: '8px 16px',
          backgroundColor: '#2196f3',
          color: 'white',
          border: 'none',
          borderRadius: 4,
          cursor: 'pointer'
        }}>
          Export Usage (30d)
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        <MetricsCard title="Requests" value={metrics.request_count} />
        <MetricsCard title="Error Rate" value={metrics.error_rate.toFixed(1)} suffix="%" />
        <MetricsCard title="Avg Latency" value={metrics.avg_latency.toFixed(0)} suffix="ms" />
        <MetricsCard title="Active Tasks" value={metrics.active_tasks} />
        <MetricsCard title="Queue Size" value={metrics.queue_size} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
        <TaskQueue tasks={tasks} />
        <APIKeyManager apiKeys={apiKeys} onUpdate={() => apiKeyService.list().then(r => setApiKeys(r.data))} />
      </div>

      <UsageAnalytics />
    </div>
  )
}