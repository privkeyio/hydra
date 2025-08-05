import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json'
  }
})

export const apiKeyService = {
  list: () => api.get('/admin/api-keys'),
  create: (data: { name: string; rate_limit?: number }) => 
    api.post('/admin/api-keys', data),
  update: (key: string, data: { name?: string; is_active?: boolean; rate_limit?: number }) =>
    api.put(`/admin/api-keys/${key}`, data),
  delete: (key: string) => api.delete(`/admin/api-keys/${key}`)
}

export const metricsService = {
  realtime: () => api.get('/admin/metrics/realtime'),
  usage: (startDate: string, endDate: string, apiKey?: string) =>
    api.get('/admin/metrics/usage', { params: { start: startDate, end: endDate, api_key: apiKey } })
}

export const taskService = {
  queue: () => api.get('/admin/tasks/queue'),
  detail: (taskId: string) => api.get(`/admin/tasks/${taskId}`)
}

export const exportService = {
  usage: (startDate: string, endDate: string) => 
    api.get('/admin/export/usage', { 
      params: { start: startDate, end: endDate },
      responseType: 'blob'
    })
}