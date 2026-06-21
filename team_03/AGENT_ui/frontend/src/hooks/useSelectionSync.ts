import { useState, useCallback } from 'react';
import type { UseWebSocketReturn } from './useWebSocket';

export interface UseSelectionSyncReturn {
  selectedId: string | null;
  source: 'graph' | 'viewport' | 'label' | null;
  /** User-initiated selection: updates local state AND broadcasts over WS. */
  select: (id: string | null, source: string) => void;
  /** Remote-initiated selection (from an incoming WS message): updates local
   *  state ONLY — never re-broadcasts, which would create an infinite echo loop. */
  applyRemoteSelection: (id: string | null, source: string) => void;
}

export function useSelectionSync(ws: UseWebSocketReturn): UseSelectionSyncReturn {
  const { send } = ws;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [source, setSource] = useState<'graph' | 'viewport' | 'label' | null>(null);

  const select = useCallback((id: string | null, src: string) => {
    setSelectedId(prev => (prev === id ? prev : id));
    setSource(src as 'graph' | 'viewport' | 'label' | null);

    // Broadcast selection to other connected clients.
    send({
      type: 'selection_sync',
      elementId: id,
      source: src,
    });
  }, [send]);

  // Applied when a selection_sync arrives over the WS. Does NOT re-send, so the
  // server's broadcast-back-to-sender cannot ping-pong into an infinite loop.
  const applyRemoteSelection = useCallback((id: string | null, src: string) => {
    setSelectedId(prev => (prev === id ? prev : id));
    setSource(src as 'graph' | 'viewport' | 'label' | null);
  }, []);

  return { selectedId, source, select, applyRemoteSelection };
}
