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

/** Structured checkpoint payload that drives the right-side options panel. */
export interface AgentCheckpoint {
  type: 'agent_checkpoint';
  agentMessage: string;
  score?: number | null;
  grade?: string | null;
  suggestions: CheckpointSuggestion[];
  rules: string[];
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
}

export interface ObserverPathMessage {
  type: 'observer_path';
  path_str: string; // "x1,y1;x2,y2;..." in layout metres
  height: number;
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
  | ChatDecision;
