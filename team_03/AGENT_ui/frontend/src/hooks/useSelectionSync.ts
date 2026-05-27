import { useState, useCallback } from 'react';
import type { UseWebSocketReturn } from './useWebSocket';

export interface UseSelectionSyncReturn {
  selectedId: string | null;
  source: 'graph' | 'viewport' | 'label' | null;
  select: (id: string | null, source: string) => void;
}

export function useSelectionSync(ws: UseWebSocketReturn): UseSelectionSyncReturn {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [source, setSource] = useState<'graph' | 'viewport' | 'label' | null>(null);

  const select = useCallback((id: string | null, src: string) => {
    setSelectedId(id);
    setSource(src as 'graph' | 'viewport' | 'label' | null);

    // Broadcast selection to other connected clients
    ws.send({
      type: 'selection_sync',
      elementId: id,
      source: src,
    });
  }, [ws]);

  return { selectedId, source, select };
}
