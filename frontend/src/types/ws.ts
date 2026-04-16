// Server → client frames
export type ServerWsFrame =
  | { type: 'output'; data: string }          // base64-encoded PTY bytes
  | { type: 'pong' }
  | { type: 'error'; message: string }
  | { type: 'session_dead'; reason: string }

// Client → server frames
export type ClientWsFrame =
  | { type: 'input'; data: string }           // raw keystrokes
  | { type: 'resize'; cols: number; rows: number }
  | { type: 'ping' }

// Union for backwards-compat consumers that don't yet distinguish direction
export type WsFrame = ServerWsFrame | ClientWsFrame
