type MessageHandler = (data: any) => void

export class WSClient {
  private ws?: WebSocket
  private url: string
  private handlers: Map<string, Set<MessageHandler>> = new Map()
  private reconnectTimer?: number
  private reconnectAttempts = 0

  constructor(url: string) {
    this.url = url
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return

    this.ws = new WebSocket(this.url)
    
    this.ws.onopen = () => {
      this.reconnectAttempts = 0
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const handlers = this.handlers.get(data.type) || []
        handlers.forEach(handler => handler(data))
      } catch (e) {}
    }

    this.ws.onclose = () => {
      this.reconnect()
    }
  }

  private reconnect() {
    if (this.reconnectTimer) return
    
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000)
    this.reconnectAttempts++
    
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = undefined
      this.connect()
    }, delay)
  }

  subscribe(type: string, handler: MessageHandler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set())
    }
    this.handlers.get(type)!.add(handler)
    
    return () => {
      this.handlers.get(type)?.delete(handler)
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = undefined
    }
    this.ws?.close()
  }
}