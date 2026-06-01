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

export type WSMessage =
  | ChatMessage
  | AgentResponse
  | AgentEvent
  | StateUpdate
  | SelectionSync;
