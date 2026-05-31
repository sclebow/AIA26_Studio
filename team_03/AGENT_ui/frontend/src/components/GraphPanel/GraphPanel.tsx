import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import {
  NODE_COLORS,
  EDGE_COLORS,
  NODE_DESCRIPTIONS,
  EDGE_DESCRIPTIONS,
  NETWORK_OPTIONS,
  getTheme,
  type GraphTheme,
} from './graphConfig';
import { mapGraphData, NodeLinkData, VisNode, VisEdge } from './graphDataMapper';
import { useTheme } from '../common/ThemeToggle';

// ── Types ───────────────────────────────────────────────────────────────────

interface GraphPanelProps {
  graphData: NodeLinkData | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  fullscreen?: boolean;
}

interface DetailInfo {
  node: VisNode;
  neighbors: { id: string; label: string; ntype: string; etype: string }[];
}

// ── Styles ──────────────────────────────────────────────────────────────────

function makeStyles(T: GraphTheme) {
  const isDark = T.canvasBg === '#08080C';

  const glassPanel: React.CSSProperties = {
    background: T.panelBg,
    border: `1px solid ${T.panelBorder}`,
    borderRadius: 10,
    color: T.text,
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
    boxShadow: isDark
      ? `0 4px 24px rgba(0,0,0,0.4), 0 0 1px ${T.accent}15`
      : '0 4px 16px rgba(0,0,0,0.08)',
  };

  return {
    container: {
      position: 'relative' as const,
      width: '100%',
      height: '100%',
      background: T.canvasBg,
      overflow: 'hidden',
    },
    canvas: {
      width: '100%',
      height: '100%',
    },
    // ── Legend panel (left) ────────────────────────────────────────
    legend: {
      ...glassPanel,
      position: 'absolute' as const,
      top: '50%',
      left: 10,
      transform: 'translateY(-50%)',
      width: 148,
      maxHeight: '78%',
      overflowY: 'auto' as const,
      padding: '5px 0',
      zIndex: 200,
      scrollbarWidth: 'none' as const,
    },
    legSection: {
      padding: '5px 10px 2px',
      fontSize: 8,
      fontWeight: 700,
      letterSpacing: '0.12em',
      textTransform: 'uppercase' as const,
      color: T.accent,
      opacity: 0.7,
    },
    legSep: {
      marginTop: 2,
      paddingTop: 5,
      borderTop: `1px solid ${T.panelBorder}`,
    },
    legItem: {
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '3px 10px',
      fontSize: 9.5,
      color: T.text,
      cursor: 'pointer',
      userSelect: 'none' as const,
      transition: 'background 0.15s, opacity 0.2s',
    },
    legDot: (color: string): React.CSSProperties => ({
      width: 7,
      height: 7,
      borderRadius: '50%',
      flexShrink: 0,
      background: color,
      boxShadow: isDark ? `0 0 6px ${color}60` : 'none',
    }),
    legLine: (color: string): React.CSSProperties => ({
      width: 14,
      height: 2,
      borderRadius: 1,
      flexShrink: 0,
      background: color,
      boxShadow: isDark ? `0 0 4px ${color}40` : 'none',
    }),
    legLabel: {
      flex: 1,
      letterSpacing: '0.02em',
    },
    legCount: {
      fontSize: 9,
      fontWeight: 600,
      color: isDark ? T.accent : T.muted,
      opacity: isDark ? 0.6 : 1,
      fontVariantNumeric: 'tabular-nums' as const,
    },
    // ── Center/fit button ──────────────────────────────────────────
    fitBtn: {
      position: 'absolute' as const,
      top: 10,
      right: 12,
      zIndex: 200,
      background: T.panelBg,
      border: `1px solid ${T.panelBorder}`,
      borderRadius: 8,
      width: 30,
      height: 30,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      color: T.muted,
      transition: 'background 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s',
      boxShadow: isDark ? `0 2px 12px rgba(0,0,0,0.3), 0 0 1px ${T.accent}10` : '0 2px 8px rgba(0,0,0,0.08)',
      padding: 0,
      outline: 'none',
    } as React.CSSProperties,
    // ── Detail panel (right) ──────────────────────────────────────
    detail: {
      ...glassPanel,
      position: 'absolute' as const,
      right: 12,
      top: '50%',
      transform: 'translateY(-50%)',
      width: 250,
      maxHeight: '80vh',
      overflow: 'hidden',
      zIndex: 200,
    },
    dpHeader: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 12px 8px',
      borderBottom: `1px solid ${T.panelBorder}`,
    },
    dpChip: (color: string): React.CSSProperties => ({
      fontSize: 8,
      fontWeight: 700,
      letterSpacing: '0.08em',
      textTransform: 'uppercase' as const,
      padding: '2px 7px',
      borderRadius: 4,
      marginRight: 6,
      background: `${color}18`,
      color,
      border: `1px solid ${color}30`,
      boxShadow: isDark ? `0 0 8px ${color}15` : 'none',
    }),
    dpName: {
      fontSize: 11,
      fontWeight: 600,
      whiteSpace: 'nowrap' as const,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      flex: 1,
      minWidth: 0,
    },
    dpClose: {
      background: 'none',
      border: 'none',
      cursor: 'pointer',
      color: T.muted,
      fontSize: 12,
      lineHeight: 1,
      padding: '3px 6px',
      borderRadius: 4,
      flexShrink: 0,
      transition: 'background 0.15s, color 0.15s',
    },
    dpScroll: {
      overflowY: 'auto' as const,
      maxHeight: 'calc(80vh - 48px)',
      padding: '8px 12px 12px',
      scrollbarWidth: 'thin' as const,
      scrollbarColor: `${T.panelBorder} transparent`,
    },
    dpDesc: {
      fontSize: 9.5,
      color: T.muted,
      lineHeight: '1.55',
      marginBottom: 8,
    },
    dpSection: {
      fontSize: 8,
      fontWeight: 700,
      letterSpacing: '0.12em',
      textTransform: 'uppercase' as const,
      color: T.accent,
      opacity: 0.7,
      margin: '8px 0 4px',
    },
    dpRow: {
      display: 'flex',
      gap: 6,
      alignItems: 'baseline',
      marginBottom: 3,
    },
    dpLbl: {
      fontSize: 9,
      color: T.muted,
      minWidth: 80,
      flexShrink: 0,
      letterSpacing: '0.02em',
    },
    dpVal: {
      fontSize: 10,
      wordBreak: 'break-word' as const,
      fontWeight: 500,
    },
    dpDivider: {
      height: 1,
      background: T.panelBorder,
      margin: '6px 0',
    },
    dpNeighbor: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      padding: '3px 0',
      borderBottom: `1px solid ${T.panelBorder}`,
      cursor: 'pointer',
      transition: 'background 0.1s',
    },
    dpNdot: (color: string): React.CSSProperties => ({
      width: 6,
      height: 6,
      borderRadius: '50%',
      flexShrink: 0,
      background: color,
      boxShadow: isDark ? `0 0 4px ${color}50` : 'none',
    }),
    dpNname: {
      flex: 1,
      fontSize: 9.5,
    },
    dpEtype: (color: string): React.CSSProperties => ({
      fontSize: 8.5,
      color,
      fontWeight: 500,
    }),
  };
}

// ── Component ───────────────────────────────────────────────────────────────

const GraphPanel: React.FC<GraphPanelProps> = ({ graphData, selectedId, onSelect, fullscreen }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesDSRef = useRef<DataSet<VisNode> | null>(null);
  const edgesDSRef = useRef<DataSet<VisEdge> | null>(null);

  const { theme: themeMode } = useTheme();
  const isDark = themeMode === 'dark';
  const THEME = getTheme(isDark);
  const styles = useMemo(() => makeStyles(THEME), [isDark]); // eslint-disable-line react-hooks/exhaustive-deps

  const [detail, setDetail] = useState<DetailInfo | null>(null);
  const [nodeFilters, setNodeFilters] = useState<Set<string>>(new Set());
  const [edgeFilters, setEdgeFilters] = useState<Set<string>>(new Set());

  // ── Derived data ────────────────────────────────────────────────
  const mapped = useMemo(() => {
    if (!graphData) return null;
    return mapGraphData(graphData, isDark);
  }, [graphData, isDark]);

  // Counts for legend
  const nodeCounts = useMemo(() => {
    if (!mapped) return {};
    const counts: Record<string, number> = {};
    mapped.nodes.forEach(n => { counts[n.ntype] = (counts[n.ntype] || 0) + 1; });
    return counts;
  }, [mapped]);

  const edgeCounts = useMemo(() => {
    if (!mapped) return {};
    const counts: Record<string, number> = {};
    mapped.edges.forEach(e => { counts[e.etype] = (counts[e.etype] || 0) + 1; });
    return counts;
  }, [mapped]);

  // Edge index for detail panel neighbors
  const edgeIndex = useMemo(() => {
    if (!mapped) return new Map<string, { etype: string; id: string }[]>();
    const idx = new Map<string, { etype: string; id: string }[]>();
    mapped.edges.forEach(e => {
      if (!idx.has(e.from)) idx.set(e.from, []);
      if (!idx.has(e.to)) idx.set(e.to, []);
      idx.get(e.from)!.push({ etype: e.etype, id: e.to });
      idx.get(e.to)!.push({ etype: e.etype, id: e.from });
    });
    return idx;
  }, [mapped]);

  const nodesById = useMemo(() => {
    if (!mapped) return new Map<string, VisNode>();
    const m = new Map<string, VisNode>();
    mapped.nodes.forEach(n => m.set(n.id, n));
    return m;
  }, [mapped]);

  // ── Open detail for a node ──────────────────────────────────────
  const openDetail = useCallback((nodeId: string) => {
    const node = nodesById.get(nodeId);
    if (!node) return;
    const conns = edgeIndex.get(nodeId) || [];
    const neighbors = conns.slice(0, 20).map(c => {
      const nb = nodesById.get(c.id);
      return {
        id: c.id,
        label: nb?.label || c.id,
        ntype: nb?.ntype || 'unknown',
        etype: c.etype,
      };
    });
    setDetail({ node, neighbors });
  }, [nodesById, edgeIndex]);

  // ── Initialize / update vis.js network ──────────────────────────
  useEffect(() => {
    if (!containerRef.current || !mapped) return;

    // Destroy previous network
    if (networkRef.current) {
      networkRef.current.destroy();
      networkRef.current = null;
    }

    const nodesDS = new DataSet(mapped.nodes as any[]);
    const edgesDS = new DataSet(mapped.edges as any[]);
    nodesDSRef.current = nodesDS;
    edgesDSRef.current = edgesDS;

    const network = new Network(
      containerRef.current,
      { nodes: nodesDS, edges: edgesDS },
      NETWORK_OPTIONS as any,
    );

    networkRef.current = network;

    // Fit on first draw
    network.once('afterDrawing', () => {
      network.fit({ animation: false });
    });

    // Click node -> select + detail
    network.on('click', (params: any) => {
      if (params.nodes && params.nodes.length > 0) {
        const nid = params.nodes[0] as string;
        onSelect(nid);
        openDetail(nid);
      } else {
        onSelect(null);
        setDetail(null);
      }
    });

    // Double-click -> zoom to node
    network.on('doubleClick', (params: any) => {
      if (params.nodes && params.nodes.length > 0) {
        network.focus(params.nodes[0], {
          scale: Math.max(network.getScale() * 1.6, 1.8),
          animation: { duration: 400, easingFunction: 'easeInOutQuad' },
        });
      }
    });

    return () => {
      network.destroy();
      networkRef.current = null;
      nodesDSRef.current = null;
      edgesDSRef.current = null;
    };
  }, [mapped, onSelect, openDetail]);

  // ── React to external selectedId changes ────────────────────────
  useEffect(() => {
    const network = networkRef.current;
    const nodesDS = nodesDSRef.current;
    if (!network || !nodesDS || !selectedId) return;

    const node = nodesById.get(selectedId);
    if (!node) return;

    // Select and highlight
    network.selectNodes([selectedId]);

    // Update visual: increase border for selected node
    nodesDS.update([{
      id: selectedId,
      borderWidth: 4,
      shadow: {
        enabled: true,
        size: 20,
        x: 0,
        y: 0,
        color: `${(NODE_COLORS as Record<string, string>)[node.ntype] || THEME.accent}66`,
      },
    }] as any);

    // Zoom to it
    network.focus(selectedId, {
      scale: Math.max(network.getScale(), 1.2),
      animation: { duration: 400, easingFunction: 'easeInOutQuad' },
    });

    openDetail(selectedId);

    // Reset border after a delay when selection changes
    return () => {
      if (nodesDSRef.current) {
        nodesDSRef.current.update([{
          id: selectedId,
          borderWidth: 2,
          shadow: { enabled: true, size: 8, x: 0, y: 2, color: 'rgba(0,0,0,0.25)' },
        }] as any);
      }
    };
  }, [selectedId, nodesById, openDetail]);

  // ── Update node font colors when theme changes ──────────────────
  useEffect(() => {
    const nodesDS = nodesDSRef.current;
    if (!nodesDS) return;
    const fontColor = THEME.nodeFontColor;
    nodesDS.update(nodesDS.get().map((n: any) => ({
      id: n.id,
      font: { ...n.font, color: fontColor },
    })));
  }, [isDark]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Apply legend filters ────────────────────────────────────────
  useEffect(() => {
    const nodesDS = nodesDSRef.current;
    const edgesDS = edgesDSRef.current;
    if (!nodesDS || !edgesDS) return;

    const nf = nodeFilters.size > 0;
    const ef = edgeFilters.size > 0;

    // Update node opacity
    nodesDS.update(nodesDS.get().map((n: any) => ({
      id: n.id,
      opacity: (!nf || nodeFilters.has(n.ntype)) ? 1.0 : 0.1,
    })));

    // Update edge opacity
    edgesDS.update(edgesDS.get().map((e: any) => {
      const fn = nodesDS.get(e.from) as any;
      const tn = nodesDS.get(e.to) as any;
      const nodeOk = !nf || (
        (fn && nodeFilters.has(fn.ntype)) ||
        (tn && nodeFilters.has(tn.ntype))
      );
      const edgeOk = !ef || edgeFilters.has(e.etype);
      const match = nodeOk && edgeOk;
      return {
        id: e.id,
        color: {
          ...e.color,
          opacity: match ? 0.7 : 0.04,
        },
      };
    }));
  }, [nodeFilters, edgeFilters]);

  // ── Legend click handlers ───────────────────────────────────────
  const handleNodeFilterClick = useCallback((ntype: string, shiftKey: boolean) => {
    setNodeFilters(prev => {
      const next = new Set(prev);
      if (shiftKey) {
        next.has(ntype) ? next.delete(ntype) : next.add(ntype);
      } else {
        if (next.size === 1 && next.has(ntype)) {
          next.clear();
        } else {
          next.clear();
          next.add(ntype);
        }
      }
      return next;
    });
  }, []);

  const handleEdgeFilterClick = useCallback((etype: string, shiftKey: boolean) => {
    setEdgeFilters(prev => {
      const next = new Set(prev);
      if (shiftKey) {
        next.has(etype) ? next.delete(etype) : next.add(etype);
      } else {
        if (next.size === 1 && next.has(etype)) {
          next.clear();
        } else {
          next.clear();
          next.add(etype);
        }
      }
      return next;
    });
  }, []);

  // ── Neighbor click in detail panel ──────────────────────────────
  const handleNeighborClick = useCallback((neighborId: string) => {
    const network = networkRef.current;
    if (!network) return;
    network.selectNodes([neighborId]);
    network.focus(neighborId, {
      animation: { duration: 400, easingFunction: 'easeInOutQuad' },
      scale: Math.max(network.getScale(), 1.2),
    });
    onSelect(neighborId);
    openDetail(neighborId);
  }, [onSelect, openDetail]);

  // ── Format a metadata value ─────────────────────────────────────
  const fmtVal = (v: unknown): string => {
    if (v === null || v === undefined) return '\u2014';
    if (typeof v === 'boolean') return v ? 'Yes' : 'No';
    if (Array.isArray(v)) return '[' + v.map(x => typeof x === 'number' ? x.toFixed(2) : String(x)).join(', ') + ']';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(3);
    return String(v);
  };

  // ── Render ──────────────────────────────────────────────────────

  if (!graphData) {
    return (
      <div style={{ ...styles.container, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: THEME.muted, fontSize: 13 }}>No graph data loaded</span>
      </div>
    );
  }

  const ANALYSIS_KEYS = new Set([
    'clearance_ok', 'reachable', 'facing_ok', 'min_clearance_m',
    'required_clearance_m', 'move_direction', 'move_distance_m', 'angle_diff',
  ]);
  const SKIP_KEYS = new Set(['id', 'ntype']);

  return (
    <div style={styles.container}>
      {/* Vis.js canvas */}
      <div ref={containerRef} style={styles.canvas} />

      {/* ── Center / fit-all button (top-right) ─────────────────── */}
      <button
        style={styles.fitBtn}
        title="Center graph"
        aria-label="Center graph"
        onClick={() => networkRef.current?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } })}
        onMouseEnter={(e) => {
          const el = e.currentTarget;
          el.style.color = THEME.accent;
          el.style.borderColor = THEME.accent;
          el.style.background = `${THEME.accent}18`;
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget;
          el.style.color = THEME.muted;
          el.style.borderColor = THEME.panelBorder;
          el.style.background = THEME.panelBg;
        }}
      >
        {/* Crosshair / target SVG */}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="22" y1="12" x2="18" y2="12" />
          <line x1="6" y1="12" x2="2" y2="12" />
          <line x1="12" y1="6" x2="12" y2="2" />
          <line x1="12" y1="22" x2="12" y2="18" />
        </svg>
      </button>

      {/* ── Legend panel (left) ─────────────────────────────────── */}
      <div style={styles.legend}>
        <div style={styles.legSection}>Nodes</div>
        {Object.entries(NODE_COLORS).map(([ntype, color]) => {
          const count = nodeCounts[ntype];
          if (!count) return null;
          const isActive = nodeFilters.has(ntype);
          const isDimmed = nodeFilters.size > 0 && !isActive;
          return (
            <div
              key={ntype}
              style={{
                ...styles.legItem,
                background: isActive ? `${THEME.accent}15` : 'transparent',
                opacity: isDimmed ? 0.25 : 1,
              }}
              onClick={(e) => handleNodeFilterClick(ntype, e.shiftKey)}
            >
              <span style={styles.legDot(color)} />
              <span style={styles.legLabel}>{ntype}</span>
              <span style={styles.legCount}>{count}</span>
            </div>
          );
        })}

        <div style={{ ...styles.legSection, ...styles.legSep }}>Edges</div>
        {Object.entries(EDGE_COLORS).map(([etype, color]) => {
          const count = edgeCounts[etype];
          if (!count) return null;
          const isActive = edgeFilters.has(etype);
          const isDimmed = edgeFilters.size > 0 && !isActive;
          return (
            <div
              key={etype}
              style={{
                ...styles.legItem,
                background: isActive ? `${THEME.accent}15` : 'transparent',
                opacity: isDimmed ? 0.25 : 1,
              }}
              title={EDGE_DESCRIPTIONS[etype] || ''}
              onClick={(e) => handleEdgeFilterClick(etype, e.shiftKey)}
            >
              <span style={styles.legLine(color)} />
              <span style={styles.legLabel}>{etype}</span>
              <span style={styles.legCount}>{count}</span>
            </div>
          );
        })}
      </div>

      {/* ── Detail panel (right) ───────────────────────────────── */}
      {detail && (
        <div style={styles.detail}>
          {/* Header */}
          <div style={styles.dpHeader}>
            <div style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
              <span style={styles.dpChip(
                (NODE_COLORS as Record<string, string>)[detail.node.ntype] || '#888'
              )}>
                {detail.node.ntype}
              </span>
              <span style={styles.dpName}>{detail.node.label}</span>
            </div>
            <button
              style={styles.dpClose}
              onClick={() => {
                setDetail(null);
                onSelect(null);
                networkRef.current?.unselectAll();
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLElement).style.color = THEME.text;
                (e.target as HTMLElement).style.background = THEME.panelBorder;
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLElement).style.color = THEME.muted;
                (e.target as HTMLElement).style.background = 'none';
              }}
            >
              {'\u2715'}
            </button>
          </div>

          {/* Scrollable body */}
          <div style={styles.dpScroll}>
            {/* Description */}
            {NODE_DESCRIPTIONS[detail.node.ntype] && (
              <div style={styles.dpDesc}>
                {NODE_DESCRIPTIONS[detail.node.ntype]}
              </div>
            )}

            {/* Properties */}
            {(() => {
              const meta = detail.node._meta;
              const propEntries = Object.entries(meta).filter(
                ([k]) => !ANALYSIS_KEYS.has(k) && !SKIP_KEYS.has(k)
              );
              if (propEntries.length === 0) return null;
              return (
                <>
                  <div style={{ ...styles.dpSection, marginTop: 0 }}>Properties</div>
                  {propEntries.map(([k, v]) => (
                    <div key={k} style={styles.dpRow}>
                      <span style={styles.dpLbl}>{k.replace(/_/g, ' ')}</span>
                      <span style={styles.dpVal}>{fmtVal(v)}</span>
                    </div>
                  ))}
                </>
              );
            })()}

            {/* Analysis */}
            {(() => {
              const meta = detail.node._meta as Record<string, any>;
              const hasAnalysis = ANALYSIS_KEYS.has('clearance_ok') && meta.clearance_ok !== undefined
                || meta.reachable !== undefined
                || meta.facing_ok !== undefined;
              if (!hasAnalysis) return null;
              return (
                <>
                  <div style={styles.dpDivider} />
                  <div style={styles.dpSection}>Analysis</div>
                  {meta.clearance_ok !== undefined && (
                    <>
                      <div style={styles.dpRow}>
                        <span style={styles.dpLbl}>clearance</span>
                        <span style={{
                          ...styles.dpVal,
                          color: meta.clearance_ok ? THEME.ok : THEME.fail,
                          fontWeight: 500,
                        }}>
                          {meta.clearance_ok ? 'OK' : 'FAIL'}
                        </span>
                      </div>
                      {!meta.clearance_ok && meta.min_clearance_m !== undefined && (
                        <div style={styles.dpRow}>
                          <span style={styles.dpLbl}>has / needs</span>
                          <span style={styles.dpVal}>
                            {fmtVal(meta.min_clearance_m)}m / {fmtVal(meta.required_clearance_m)}m
                          </span>
                        </div>
                      )}
                      {!meta.clearance_ok && meta.move_direction && (
                        <div style={styles.dpRow}>
                          <span style={styles.dpLbl}>suggested fix</span>
                          <span style={{ ...styles.dpVal, color: THEME.accent, fontWeight: 500 }}>
                            move {fmtVal(meta.move_direction)} {'\u00b7'} {fmtVal(meta.move_distance_m)}m
                          </span>
                        </div>
                      )}
                    </>
                  )}
                  {meta.reachable !== undefined && (
                    <div style={styles.dpRow}>
                      <span style={styles.dpLbl}>reachable</span>
                      <span style={{
                        ...styles.dpVal,
                        color: meta.reachable ? THEME.ok : THEME.fail,
                        fontWeight: 500,
                      }}>
                        {meta.reachable ? 'YES' : 'NO'}
                      </span>
                    </div>
                  )}
                  {meta.facing_ok !== undefined && (
                    <div style={styles.dpRow}>
                      <span style={styles.dpLbl}>facing</span>
                      <span style={{
                        ...styles.dpVal,
                        color: meta.facing_ok ? THEME.ok : THEME.warn,
                        fontWeight: 500,
                      }}>
                        {meta.facing_ok ? 'OK' : `off ${fmtVal(meta.angle_diff)}\u00b0`}
                      </span>
                    </div>
                  )}
                </>
              );
            })()}

            {/* Connections */}
            {detail.neighbors.length > 0 && (
              <>
                <div style={styles.dpDivider} />
                <div style={styles.dpSection}>
                  Connections ({(edgeIndex.get(detail.node.id) || []).length})
                </div>
                {detail.neighbors.map((nb, i) => {
                  const nbColor = (NODE_COLORS as Record<string, string>)[nb.ntype] || '#888';
                  const eColor = (EDGE_COLORS as Record<string, string>)[nb.etype] || '#888';
                  return (
                    <div
                      key={`${nb.id}-${nb.etype}-${i}`}
                      style={{
                        ...styles.dpNeighbor,
                        ...(i === detail.neighbors.length - 1 ? { borderBottom: 'none' } : {}),
                      }}
                      onClick={() => handleNeighborClick(nb.id)}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.background = THEME.panelBorder;
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.background = 'transparent';
                      }}
                    >
                      <span style={styles.dpNdot(nbColor)} />
                      <span style={styles.dpNname}>{nb.label}</span>
                      <span style={styles.dpEtype(eColor)}>{nb.etype}</span>
                    </div>
                  );
                })}
                {(edgeIndex.get(detail.node.id) || []).length > 20 && (
                  <div style={{ fontSize: 9, color: THEME.muted, marginTop: 4 }}>
                    +{(edgeIndex.get(detail.node.id) || []).length - 20} more
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphPanel;
