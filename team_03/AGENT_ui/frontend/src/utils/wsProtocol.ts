import type { ToolCallCardProps } from '../components/ChatPanel/ToolCallCard';

export interface ChatMessage {
  type: 'chat_message';
  content: string;
}

export interface AgentResponse {
  type: 'agent_response';
  content: string;
  tool_calls?: ToolCallCardProps[];
}

/** A chat line from the agent (narrative / streamed text). */
export interface AgentSay {
  type: 'agent_say';
  content: string;
}

export interface CheckpointSuggestion {
  key: string;   // "s1".."s5"
  label: string;
}

/** A furniture change reported at a checkpoint (ADDED / MOVED + detail). */
export interface CheckpointChange {
  action: string;   // "ADDED" | "MOVED"
  text: string;     // "desk   at (1.0, 2.0)  [workshop]"
}

/** Structured checkpoint payload that drives the right-side options panel. */
export interface AgentCheckpoint {
  type: 'agent_checkpoint';
  agentMessage: string;
  score?: number | null;
  prevScore?: number | null;
  grade?: string | null;
  suggestions: CheckpointSuggestion[];
  rules: string[];
  violations?: string[];
  changes?: CheckpointChange[];
  doorChanges?: string[];
  actions: { approve: boolean; end: boolean; yes: boolean };
}

/** A decision selected from the options panel (chip token), sent to the agent. */
export interface ChatDecision {
  type: 'chat_decision';
  value: string;
}

export interface AgentEvent {
  type: 'agent_event';
  node: string;
  status: 'started' | 'completed' | 'error';
  data?: unknown;
}

export interface StateUpdate {
  type: 'state_update';
  field: 'layout' | 'graph' | 'scores';
  data: unknown;
  proposal?: boolean;
}

export interface SelectionSync {
  type: 'selection_sync';
  elementId: string | null;
  source: string;
}

export interface ObserverPoint {
  type: 'observer_point';
  x: number;
  y: number;
  height: number;
  point_str: string; // "x,y,h" in layout metres
  /** When true: skip MCP/GH push, compute Python isovist only (fast drag path). */
  live?: boolean;
}

export interface ObserverPathMessage {
  type: 'observer_path';
  path_str: string; // "x1,y1;x2,y2;..." in layout metres
  height: number;
}

/** Result of a set_observer run: the visibility isovist polygon to draw. */
export interface ObserverResult {
  type: 'observer_result';
  mode: 'person' | 'path';
  status: string;
  isovist: [number, number][] | null; // closed polygon in layout metres
  /** Present when the chat agent placed the observer — draws a read-only ghost marker. */
  agentObserver?: { mode: 'person' | 'path'; point?: [number, number]; path?: [number, number][] } | null;
}

/** Collision / orientation analysis overlay — drives the Three.js viewport heatmap. */
export interface AnalysisOverlay {
  type: 'analysis_overlay';
  kind: 'collision' | 'orientation';
  /** Collision grid: cell indices + grid metadata (layout metres). */
  grid_viz?: {
    violation_cells: number[];
    warning_cells: number[];
    ox: number; oy: number;
    cols: number; rows: number;
    cs: number;
  };
  /** Orientation: one entry per object that has an 'orientation' field. */
  results?: Array<{
    object_id: string;
    name: string;
    facing_ok: boolean;
    angle_diff: number;
    orientation_deg: number;
    target_direction_deg: number;
  }>;
}

/** One recorded pipeline run for the Benchmark dashboard. */
export interface BenchRun {
  run_id: string;
  started_at: number;
  ended_at: number;
  status: 'ok' | 'error' | 'aborted';
  provider: string;
  model: string;
  model_label: string;
  layout_name: string;
  prompt: string;
  workflow: {
    duration_s: number;
    duration_min: number;
    reason_turns: number;
    turns_per_zone: number;
    api_calls: number;
    tool_calls: number;
    recursion_hits: number;
    checkpoints: number;
    category_calls: Record<string, number>;
    gantt: Array<{ node: string; start_ms: number; total_ms: number; count: number }>;
  };
  scoring: {
    overall: number;
    grade: string;
    metrics: Record<string, number>;
    weights: Record<string, number>;
  } | null;
  placement: Record<string, unknown> | null;
  timeline: Array<{ t_ms: number; node: string; status: string; detail?: string }>;
}

/** Per-model aggregate row. */
export interface BenchModelAgg {
  label: string;
  provider: string;
  runs: number;
  overall: number | null;
  metrics: Record<string, number | null>;
  avg_duration_s: number | null;
  avg_turns: number | null;
  avg_api_calls: number | null;
}

export interface BenchmarkData {
  runs: BenchRun[];
  aggregate: { models: BenchModelAgg[]; metrics: string[] };
  count: number;
}

/** A pipeline run just finished and was recorded → refresh the dashboard. */
export interface BenchmarkUpdate {
  type: 'benchmark_update';
  run: BenchRun;
}

/** A new revision was saved to team_03/output/ (e.g. after Approve layout). */
export interface VersionSaved {
  type: 'version_saved';
  file: string;          // output file name, e.g. "industrial_005_2026-06-07_22-41_final.json"
  id: string;            // file stem
  name?: string | null;  // base layout name the revision belongs to
}

export type WSMessage =
  | ChatMessage
  | AgentResponse
  | AgentSay
  | AgentCheckpoint
  | AgentEvent
  | StateUpdate
  | SelectionSync
  | ObserverPoint
  | ObserverPathMessage
  | ObserverResult
  | AnalysisOverlay
  | VersionSaved
  | BenchmarkUpdate
  | ChatDecision;
