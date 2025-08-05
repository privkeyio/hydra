import { Task } from '../types'

interface TaskQueueProps {
  tasks: Task[]
}

export function TaskQueue({ tasks }: TaskQueueProps) {
  const statusColors = {
    pending: '#ff9800',
    in_progress: '#2196f3',
    completed: '#4caf50',
    failed: '#f44336'
  }

  return (
    <div style={{ border: '1px solid #e0e0e0', borderRadius: 8, padding: 20 }}>
      <h2 style={{ margin: '0 0 20px' }}>Task Queue</h2>
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {tasks.map(task => (
          <div key={task.id} style={{ 
            padding: 12, 
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div>
              <div style={{ fontWeight: 'bold' }}>{task.id.slice(0, 8)}</div>
              <div style={{ fontSize: 12, color: '#666' }}>
                {new Date(task.created_at).toLocaleString()}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              {task.progress !== undefined && (
                <div style={{ width: 100, height: 6, backgroundColor: '#e0e0e0', borderRadius: 3 }}>
                  <div style={{ 
                    width: `${task.progress}%`, 
                    height: '100%', 
                    backgroundColor: '#2196f3',
                    borderRadius: 3,
                    transition: 'width 0.3s'
                  }} />
                </div>
              )}
              <span style={{ 
                color: statusColors[task.status],
                fontSize: 12,
                fontWeight: 'bold'
              }}>
                {task.status.toUpperCase()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}