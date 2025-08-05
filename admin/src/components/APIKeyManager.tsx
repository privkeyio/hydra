import { useState } from 'react'
import { APIKey } from '../types'
import { apiKeyService } from '../services/api'

interface APIKeyManagerProps {
  apiKeys: APIKey[]
  onUpdate: () => void
}

export function APIKeyManager({ apiKeys, onUpdate }: APIKeyManagerProps) {
  const [showCreate, setShowCreate] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyLimit, setNewKeyLimit] = useState('1000')

  const handleCreate = async () => {
    try {
      await apiKeyService.create({ 
        name: newKeyName, 
        rate_limit: parseInt(newKeyLimit) 
      })
      setNewKeyName('')
      setNewKeyLimit('1000')
      setShowCreate(false)
      onUpdate()
    } catch (e) {}
  }

  const handleToggle = async (key: string, isActive: boolean) => {
    try {
      await apiKeyService.update(key, { is_active: !isActive })
      onUpdate()
    } catch (e) {}
  }

  const handleDelete = async (key: string) => {
    if (confirm('Delete this API key?')) {
      try {
        await apiKeyService.delete(key)
        onUpdate()
      } catch (e) {}
    }
  }

  return (
    <div style={{ border: '1px solid #e0e0e0', borderRadius: 8, padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>API Keys</h2>
        <button onClick={() => setShowCreate(true)} style={{
          padding: '8px 16px',
          backgroundColor: '#2196f3',
          color: 'white',
          border: 'none',
          borderRadius: 4,
          cursor: 'pointer'
        }}>
          New Key
        </button>
      </div>

      {showCreate && (
        <div style={{ marginBottom: 20, padding: 16, backgroundColor: '#f5f5f5', borderRadius: 4 }}>
          <input
            type="text"
            placeholder="Key name"
            value={newKeyName}
            onChange={e => setNewKeyName(e.target.value)}
            style={{ marginRight: 8, padding: 8, border: '1px solid #ddd', borderRadius: 4 }}
          />
          <input
            type="number"
            placeholder="Rate limit"
            value={newKeyLimit}
            onChange={e => setNewKeyLimit(e.target.value)}
            style={{ marginRight: 8, padding: 8, border: '1px solid #ddd', borderRadius: 4, width: 100 }}
          />
          <button onClick={handleCreate} style={{
            padding: '8px 16px',
            backgroundColor: '#4caf50',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            marginRight: 8
          }}>
            Create
          </button>
          <button onClick={() => setShowCreate(false)} style={{
            padding: '8px 16px',
            backgroundColor: '#f44336',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer'
          }}>
            Cancel
          </button>
        </div>
      )}

      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {apiKeys.map(apiKey => (
          <div key={apiKey.key} style={{
            padding: 12,
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div>
              <div style={{ fontWeight: 'bold' }}>{apiKey.name}</div>
              <div style={{ fontSize: 12, color: '#666' }}>
                {apiKey.key.slice(0, 8)}... • Limit: {apiKey.rate_limit}/min
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => handleToggle(apiKey.key, apiKey.is_active)} style={{
                padding: '4px 12px',
                backgroundColor: apiKey.is_active ? '#4caf50' : '#ff9800',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 12
              }}>
                {apiKey.is_active ? 'Active' : 'Inactive'}
              </button>
              <button onClick={() => handleDelete(apiKey.key)} style={{
                padding: '4px 12px',
                backgroundColor: '#f44336',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 12
              }}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}