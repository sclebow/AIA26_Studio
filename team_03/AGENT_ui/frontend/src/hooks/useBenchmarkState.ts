import { useCallback, useEffect, useState } from 'react';
import type { BenchmarkData, BenchmarkUpdate } from '../utils/wsProtocol';

const EMPTY: BenchmarkData = {
  runs: [],
  aggregate: { models: [], metrics: ['collision', 'visibility', 'path', 'reachability', 'orientation'] },
  count: 0,
};

export interface UseBenchmarkStateReturn {
  data: BenchmarkData;
  loading: boolean;
  /** Re-fetch the full history + aggregates from the backend. */
  refresh: () => Promise<void>;
  /** Wipe the entire benchmark history. */
  clear: () => Promise<void>;
  /** Feed a `benchmark_update` WS message (a run just finished → refresh). */
  handleBenchmarkUpdate: (msg: BenchmarkUpdate) => void;
}

/**
 * Owns the benchmark history shown in the Benchmark dashboard. The backend
 * auto-records every pipeline run; this hook fetches `/api/benchmarks` on mount
 * and whenever a `benchmark_update` arrives over the WebSocket, so the charts
 * stay live without polling.
 */
export function useBenchmarkState(): UseBenchmarkStateReturn {
  const [data, setData] = useState<BenchmarkData>(EMPTY);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/benchmarks');
      if (res.ok) {
        const json = (await res.json()) as BenchmarkData;
        setData({
          runs: json.runs ?? [],
          aggregate: json.aggregate ?? EMPTY.aggregate,
          count: json.count ?? (json.runs ? json.runs.length : 0),
        });
      }
    } catch {
      /* leave previous data on failure */
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(async () => {
    try {
      await fetch('/api/benchmarks', { method: 'DELETE' });
    } catch {
      /* ignore */
    }
    setData(EMPTY);
  }, []);

  // A run just finished → re-fetch so aggregates recompute server-side.
  const handleBenchmarkUpdate = useCallback((_msg: BenchmarkUpdate) => {
    void refresh();
  }, [refresh]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { data, loading, refresh, clear, handleBenchmarkUpdate };
}
