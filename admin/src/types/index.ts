export interface APIKey {
  key: string
  name: string
  created_at: string
  is_active: boolean
  rate_limit: number
}

export interface Task {
  id: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  created_at: string
  completed_at?: string
  agent_count: number
  progress?: number
}

export interface Metrics {
  request_count: number
  error_rate: number
  avg_latency: number
  active_tasks: number
  queue_size: number
}

export interface UsageData {
  timestamp: string
  api_key_id?: string
  endpoint: string
  tokens_used: number
  task_id?: string
}