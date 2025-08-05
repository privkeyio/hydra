import Papa from 'papaparse'
import { exportService } from '../services/api'

export async function exportUsageToCSV(startDate: string, endDate: string) {
  try {
    const response = await exportService.usage(startDate, endDate)
    const blob = new Blob([response.data], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `usage_${startDate}_to_${endDate}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (e) {
    throw e
  }
}