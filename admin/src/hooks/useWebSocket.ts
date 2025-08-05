import { useEffect, useRef } from 'react'
import { WSClient } from '../services/websocket'

export function useWebSocket(url: string) {
  const clientRef = useRef<WSClient>()

  useEffect(() => {
    const client = new WSClient(url)
    clientRef.current = client
    client.connect()

    return () => {
      client.disconnect()
    }
  }, [url])

  return clientRef.current
}