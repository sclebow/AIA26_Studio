import { useState, useCallback, useRef } from 'react';
import type { LayoutJSON } from '../types';
import type { NodeLinkData } from '../components/GraphPanel/graphDataMapper';
import type { ScoreData } from '../components/Dashboard/Dashboard';
import type { LayoutInfo } from '../components/LayoutLoader/LayoutLoader';
import type { StateUpdate } from '../utils/wsProtocol';

const API_BASE = '/api';

/** Compare two layouts and return the set of element IDs that were added or moved. */
function diffLayoutIds(oldLayout: LayoutJSON | null, newLayout: LayoutJSON): Set<string> {
  const modified = new Set<string>();
  if (!oldLayout) return modified;

  const layers: (keyof Pick<LayoutJSON, 'rooms' | 'doors' | 'windows' | 'furniture' | 'mep' | 'structure'>)[] =
    ['rooms', 'doors', 'windows', 'furniture', 'mep', 'structure'];

  for (const layer of layers) {
    const oldItems = oldLayout[layer] || [];
    const newItems = newLayout[layer] || [];

    // Build a map of old items by id → serialized geometry
    const oldMap = new Map<string, string>();
    for (const item of oldItems) {
      oldMap.set(item.id, JSON.stringify(item.geometry));
    }

    for (const item of newItems) {
      const oldGeo = oldMap.get(item.id);
      if (oldGeo === undefined) {
        // New element
        modified.add(item.id);
      } else if (oldGeo !== JSON.stringify(item.geometry)) {
        // Geometry changed (moved/reshaped)
        modified.add(item.id);
      }
    }
  }

  return modified;
}

/** NetworkX node_link_data uses "edges" key; our frontend expects "links". Normalize. */
function normalizeGraphData(data: Record<string, unknown>): NodeLinkData | null {
  if (!data || data.error) return null;
  const nodes = data.nodes as NodeLinkData['nodes'];
  // Accept both "links" and "edges" keys
  const links = (data.links ?? data.edges ?? []) as NodeLinkData['links'];
  return {
    directed: data.directed as boolean ?? false,
    multigraph: data.multigraph as boolean ?? true,
    graph: (data.graph as Record<string, unknown>) ?? {},
    nodes,
    links,
  };
}

/** One entry in a layout's version history (original + approved revisions). */
export interface VersionInfo {
  id: string;            // base name (original) or output file stem (revision)
  label: string;         // "Original" | "2026-06-07 22:41"
  kind: 'original' | 'version';
  file: string | null;   // output file name (revisions only)
  timestamp: number;     // file mtime (epoch seconds)
  file_size: number;
}

export interface UseLayoutStateReturn {
  layout: LayoutJSON | null;
  graphData: NodeLinkData | null;
  scores: ScoreData | null;
  availableLayouts: LayoutInfo[];
  selectedLayoutName: string | null;
  modifiedIds: Set<string>;
  isPending: boolean;
  versions: VersionInfo[];
  selectedVersionId: string | null;
  loadLayout: (name: string) => Promise<void>;
  reloadLayout: () => Promise<void>;
  uploadLayout: (file: File) => Promise<void>;
  fetchLayouts: () => Promise<void>;
  fetchVersions: (name?: string) => Promise<VersionInfo[]>;
  selectVersion: (versionId: string, file: string | null) => Promise<void>;
  updateFromWS: (message: StateUpdate) => void;
  setScores: (scores: ScoreData) => void;
  acceptPending: () => Promise<void>;
  rejectPending: () => void;
  /** Show a layout object in the viewport without committing it (AI generator preview). */
  previewLayout: (data: LayoutJSON) => void;
  /** Restore the committed layout after previewing (cancel a preview). */
  endPreview: () => void;
  /** Persist a generated layout to AI_GENERATED, refresh the list, and load it as active. */
  saveAndLoadGenerated: (name: string, data: LayoutJSON) => Promise<string | null>;
}

export function useLayoutState(): UseLayoutStateReturn {
  const [layout, setLayout] = useState<LayoutJSON | null>(null);
  const [graphData, setGraphData] = useState<NodeLinkData | null>(null);
  const [scores, setScores] = useState<ScoreData | null>(null);
  const [availableLayouts, setAvailableLayouts] = useState<LayoutInfo[]>([]);
  const [selectedLayoutName, setSelectedLayoutName] = useState<string | null>(null);
  const [modifiedIds, setModifiedIds] = useState<Set<string>>(new Set());
  const [isPending, setIsPending] = useState(false);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const layoutRef = useRef<LayoutJSON | null>(null);
  const preProposalRef = useRef<LayoutJSON | null>(null);
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Update layout with diffing — highlights modified elements for 6 seconds */
  const setLayoutWithDiff = useCallback((newLayout: LayoutJSON) => {
    const diff = diffLayoutIds(layoutRef.current, newLayout);
    layoutRef.current = newLayout;
    setLayout(newLayout);

    if (diff.size > 0) {
      setModifiedIds(diff);
      // Auto-clear highlights after 6 seconds
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
      clearTimerRef.current = setTimeout(() => {
        setModifiedIds(new Set());
      }, 6000);
    }
  }, []);

  const fetchLayouts = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/layouts`);
      if (res.ok) {
        const data = await res.json();
        setAvailableLayouts(data);
      }
    } catch {
      // API not available, that's ok
    }
  }, []);

  /** Fetch the version history (original + revisions) for a base layout. */
  const fetchVersions = useCallback(async (name?: string): Promise<VersionInfo[]> => {
    const target = name ?? selectedLayoutName;
    if (!target) { setVersions([]); return []; }
    try {
      const res = await fetch(`${API_BASE}/layouts/${encodeURIComponent(target)}/versions`);
      if (res.ok) {
        const data = (await res.json()) as VersionInfo[];
        setVersions(data);
        return data;
      }
    } catch {
      // versions endpoint unavailable — leave the list empty
    }
    return [];
  }, [selectedLayoutName]);

  /** Make a specific version (original or a saved revision) the active layout.
   *  Loads it into the viewport, mirrors it into the working session, and pins
   *  it server-side so the chat pipeline runs on this revision. */
  const selectVersion = useCallback(async (versionId: string, file: string | null) => {
    const base = selectedLayoutName;
    if (!base) return;
    setSelectedVersionId(versionId);
    try {
      const res = await fetch(`${API_BASE}/layouts/${encodeURIComponent(base)}/version/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_id: versionId, file }),
      });
      if (!res.ok) return;
      const data = (await res.json()) as LayoutJSON;
      setLayoutWithDiff(data);
      // The backend rebuilt the spatial graph for this revision — pull it.
      try {
        const g = await fetch(`${API_BASE}/graph`);
        if (g.ok) {
          const gd = await g.json();
          if (gd) setGraphData(normalizeGraphData(gd));
        }
      } catch { /* keep existing graph */ }
    } catch {
      // selection failed — viewport keeps the current layout
    }
  }, [selectedLayoutName, setLayoutWithDiff]);

  const loadLayout = useCallback(async (name: string) => {
    try {
      setSelectedLayoutName(name);
      // Loading a base layout resets the version selection to its "current"
      // working state (the original id); the history list is refreshed by App.
      setSelectedVersionId(name);

      // Try to load active session layout first (post-approval state)
      // Falls back to base layout if no session exists
      let layoutData = null;
      try {
        const sessionRes = await fetch(`${API_BASE}/layouts/${encodeURIComponent(name)}/reload`, { method: 'POST' });
        if (sessionRes.ok) {
          layoutData = await sessionRes.json();
        }
      } catch { /* ignore */ }

      if (!layoutData) {
        const layoutRes = await fetch(`${API_BASE}/layouts/${encodeURIComponent(name)}`);
        if (layoutRes.ok) layoutData = await layoutRes.json();
      }

      if (layoutData) {
        layoutRef.current = layoutData;
        setLayout(layoutData);
      }

      // Create/update session and fetch graph data
      try {
        await fetch(`${API_BASE}/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ layout_name: name }),
        });
      } catch {
        // Session endpoint may not be available
      }

      try {
        const graphRes = await fetch(`${API_BASE}/graph`);
        if (graphRes.ok) {
          const gData = await graphRes.json();
          if (gData) {
            setGraphData(normalizeGraphData(gData));
          }
        }
      } catch {
        // Graph endpoint may not be available
      }

      try {
        const scoresRes = await fetch(`${API_BASE}/scores`);
        if (scoresRes.ok) {
          const sData = await scoresRes.json();
          setScores(sData);
        }
      } catch {
        // Scores endpoint may not be available
      }

      // Fetch version history — use `name` directly (avoids stale-closure issues
      // with selectedLayoutName which hasn't propagated yet at this point).
      try {
        const vRes = await fetch(`${API_BASE}/layouts/${encodeURIComponent(name)}/versions`);
        if (vRes.ok) {
          const vData = (await vRes.json()) as VersionInfo[];
          setVersions(vData);
          // Mark the original (base) as current if no revision is pinned.
          setSelectedVersionId(name);
        }
      } catch {
        // versions endpoint may not be available
      }
    } catch {
      // Layout fetch failed
    }
  }, []);

  /** Force re-read the current layout from disk (via backend reload endpoint) */
  const reloadLayout = useCallback(async () => {
    if (!selectedLayoutName) return;
    const enc = encodeURIComponent(selectedLayoutName);

    const applyFresh = async (freshData: LayoutJSON) => {
      // Did objects get added/moved? Only then refresh the (heavier) graph.
      const changed = diffLayoutIds(layoutRef.current, freshData).size > 0;
      setLayoutWithDiff(freshData);
      if (changed) {
        // The backend rebuilds the spatial graph on reload — pull it so newly
        // placed furniture + relations appear in the Spatial Graph panel.
        try {
          const g = await fetch(`${API_BASE}/graph`);
          if (g.ok) {
            const gd = await g.json();
            if (gd) setGraphData(normalizeGraphData(gd));
          }
        } catch {
          // Graph endpoint unavailable — keep the existing graph
        }
      }
    };

    try {
      const res = await fetch(`${API_BASE}/layouts/${enc}/reload`, { method: 'POST' });
      if (res.ok) await applyFresh(await res.json());
    } catch {
      // Reload endpoint not available, try GET
      try {
        const res = await fetch(`${API_BASE}/layouts/${enc}`);
        if (res.ok) await applyFresh(await res.json());
      } catch {
        // Ignore
      }
    }
  }, [selectedLayoutName, setLayoutWithDiff]);

  const uploadLayout = useCallback(async (file: File) => {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_BASE}/layouts/upload`, {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        // Refresh layout list
        await fetchLayouts();
        // If upload returns layout data, load it
        if (data.layout) {
          setLayout(data.layout);
          setSelectedLayoutName(data.name ?? file.name.replace('.json', ''));
        } else if (data.name) {
          // Load the uploaded layout by name
          await loadLayout(data.name);
        }
      }
    } catch {
      // Upload failed, try loading file directly as layout
      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as LayoutJSON;
        setLayout(parsed);
        setSelectedLayoutName(file.name.replace('.json', ''));
      } catch {
        // Could not parse file
      }
    }
  }, [fetchLayouts, loadLayout]);

  const acceptPending = useCallback(async () => {
    const current = layout;
    if (!current) return;

    // Promote the displayed (proposed) layout to the committed state
    layoutRef.current = current;
    setIsPending(false);
    preProposalRef.current = null;

    // Auto-clear highlights after 6s
    if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
    clearTimerRef.current = setTimeout(() => {
      setModifiedIds(new Set());
    }, 6000);

    // Persist to disk
    if (selectedLayoutName) {
      try {
        await fetch(`${API_BASE}/layouts/${encodeURIComponent(selectedLayoutName)}/commit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ layout: current }),
        });
      } catch {
        // Commit to disk failed — local state is still accepted
      }
    }
  }, [layout, selectedLayoutName]);

  const rejectPending = useCallback(() => {
    const original = preProposalRef.current;
    if (!original) return;

    layoutRef.current = original;
    setLayout(original);
    preProposalRef.current = null;
    setIsPending(false);
    setModifiedIds(new Set());
    if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
  }, []);

  // ── AI Layout Generator ────────────────────────────────────────────────
  /** Display-only preview of a candidate layout — does NOT touch layoutRef /
   *  selectedLayoutName / graph, so endPreview() can restore the committed one. */
  const previewLayout = useCallback((data: LayoutJSON) => {
    setModifiedIds(new Set());
    if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
    setLayout(data);
  }, []);

  /** Restore the last committed layout (cancel a preview / close the generator). */
  const endPreview = useCallback(() => {
    setLayout(layoutRef.current);
  }, []);

  /** Save a generated layout to AI_GENERATED then load it as the active layout
   *  (loadLayout sets layoutRef + selectedLayoutName + rebuilds session/graph).
   *  Returns the saved stem name, or null on failure. */
  const saveAndLoadGenerated = useCallback(
    async (name: string, data: LayoutJSON): Promise<string | null> => {
      try {
        const res = await fetch(`${API_BASE}/layouts/generated/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, layout: data }),
        });
        if (!res.ok) return null;
        const saved = await res.json();
        const savedName: string = saved.name ?? name;
        await fetchLayouts();
        await loadLayout(savedName);
        return savedName;
      } catch {
        return null;
      }
    },
    [fetchLayouts, loadLayout]
  );

  const updateFromWS = useCallback((message: StateUpdate) => {
    switch (message.field) {
      case 'layout':
        if (message.proposal) {
          // Save original layout for potential revert (only if not already pending)
          if (!preProposalRef.current) {
            preProposalRef.current = layoutRef.current;
          }
          const proposed = message.data as LayoutJSON;
          setIsPending(true);
          // Show proposed layout in viewport but don't update layoutRef
          setLayout(proposed);
          // Compute diff for pulse highlights (no auto-clear while pending)
          const diff = diffLayoutIds(preProposalRef.current, proposed);
          if (diff.size > 0) {
            setModifiedIds(diff);
            if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
          }
        } else {
          setLayoutWithDiff(message.data as LayoutJSON);
        }
        break;
      case 'graph':
        setGraphData(normalizeGraphData(message.data as Record<string, unknown>));
        break;
      case 'scores':
        setScores(message.data as ScoreData);
        break;
    }
  }, [setLayoutWithDiff]);

  return {
    layout,
    graphData,
    scores,
    availableLayouts,
    selectedLayoutName,
    modifiedIds,
    isPending,
    versions,
    selectedVersionId,
    loadLayout,
    reloadLayout,
    uploadLayout,
    fetchLayouts,
    fetchVersions,
    selectVersion,
    updateFromWS,
    setScores,
    acceptPending,
    rejectPending,
    previewLayout,
    endPreview,
    saveAndLoadGenerated,
  };
}
