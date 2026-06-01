import { useState, useEffect, useRef, useCallback } from 'react';
import type { WSMessage } from '../utils/wsProtocol';

// Use the current host so Vite's proxy handles the WS connection in dev mode
const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const RECONNECT_DELAY = 3000;

export interface UseWebSocketReturn {
  send: (message: WSMessage) => void;
  lastMessage: WSMessage | null;
  isConnected: boolean;
  /** Subscribe to EVERY incoming message (no drops). Returns an unsubscribe fn.
   *  Prefer this over `lastMessage` for dispatching — `lastMessage` is a single
   *  slot and coalesces messages that arrive in the same tick (losing some). */
  subscribe: (handler: (msg: WSMessage) => void) => () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const handlersRef = useRef<Set<(msg: WSMessage) => void>>(new Set());

  const subscribe = useCallback((handler: (msg: WSMessage) => void) => {
    handlersRef.current.add(handler);
    return () => { handlersRef.current.delete(handler); };
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (mountedRef.current) {
          setIsConnected(true);
        }
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data) as WSMessage;
          // Deliver to every subscriber synchronously — no message is dropped
          // even when several arrive in the same tick.
          handlersRef.current.forEach(fn => { try { fn(parsed); } catch { /* ignore */ } });
          setLastMessage(parsed);
        } catch {
          // Ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        wsRef.current = null;
        // Schedule reconnect
        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, RECONNECT_DELAY);
      };

      ws.onerror = () => {
        // onclose will fire after onerror, triggering reconnect
        ws.close();
      };
    } catch {
      // Schedule reconnect on connection failure
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, RECONNECT_DELAY);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const send = useCallback((message: WSMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  return { send, lastMessage, isConnected, subscribe };
}
