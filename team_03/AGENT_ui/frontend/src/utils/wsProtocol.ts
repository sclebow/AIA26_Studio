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
  | AgentEvent
  | StateUpdate
  | SelectionSync
  | ObserverPoint
  | ObserverPathMessage;
