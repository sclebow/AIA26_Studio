import { useState, useCallback } from 'react';
import type { Message } from '../components/ChatPanel/MessageBubble';
import type { NodeStatus } from '../components/ProcessPanel/ToolStatusCard';
import type { AgentEvent, AgentResponse, AgentSay, AgentCheckpoint } from '../utils/wsProtocol';
import type { LogEntry } from '../components/ReasoningLog/ReasoningLog';
import type { ScoreData } from '../components/Dashboard/Dashboard';

/** Active checkpoint options shown in the chat's right-side panel. */
export interface CheckpointState {
  agentMessage: string;
  score?: number | null;
  grade?: string | null;
  suggestions: { key: string; label: string }[];
  rules: string[];
  actions: { approve: boolean; end: boolean; yes: boolean };
}

export interface UseAgentStateReturn {
  messages: Message[];
  nodeStatuses: Record<string, NodeStatus>;
  isAgentRunning: boolean;
  logEntries: LogEntry[];
  checkpoint: CheckpointState | null;
  addUserMessage: (content: string) => void;
  beginAwaitingResponse: () => void;
  handleAgentEvent: (event: AgentEvent) => void;
  handleAgentResponse: (response: AgentResponse) => void;
  handleAgentSay: (msg: AgentSay) => void;
  handleAgentCheckpoint: (cp: AgentCheckpoint) => void;
  resetChat: () => void;
  cancelLast: () => void;
}

let messageCounter = 0;
let logCounter = 0;

export interface UseAgentStateOptions {
  onScoresReady?: (scores: ScoreData) => void;
}

export function useAgentState(options?: UseAgentStateOptions): UseAgentStateReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [checkpoint, setCheckpoint] = useState<CheckpointState | null>(null);
  void options; // onScoresReady reserved for future real-score wiring

  const addLog = useCallback((type: LogEntry['type'], message: string, node?: string, data?: unknown) => {
    setLogEntries(prev => [...prev, {
      id: `log-${++logCounter}-${Date.now()}`,
      timestamp: Date.now(),
      type,
      node,
      message,
      data,
    }]);
  }, []);

  const addUserMessage = useCallback((content: string) => {
    const msg: Message = {
      id: `user-${++messageCounter}-${Date.now()}`,
      role: 'user',
      content,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, msg]);
    setIsAgentRunning(true);
    setCheckpoint(null);   // a new instruction supersedes the old options
    addLog('info', `User prompt: "${content.length > 80 ? content.slice(0, 80) + '...' : content}"`);
  }, [addLog]);

  // Mark the agent as working after a decision/chip (no new user bubble).
  const beginAwaitingResponse = useCallback(() => {
    setIsAgentRunning(true);
    setCheckpoint(null);
  }, []);

  const handleAgentEvent = useCallback((event: AgentEvent) => {
    const statusMap: Record<string, NodeStatus> = {
      started: 'running',
      completed: 'completed',
      error: 'error',
    };

    setNodeStatuses(prev => ({
      ...prev,
      [event.node]: statusMap[event.status] ?? 'pending',
    }));

    if (event.status === 'started') {
      setIsAgentRunning(true);
      addLog('node_start', 'Started', event.node);
    } else if (event.status === 'completed') {
      addLog('node_complete', event.data ? `Completed — ${typeof event.data === 'string' ? event.data : JSON.stringify(event.data).slice(0, 120)}` : 'Completed', event.node, event.data);
    } else if (event.status === 'error') {
      addLog('node_error', event.data ? `Error: ${event.data}` : 'Error occurred', event.node, event.data);
    }
  }, [addLog]);

  const handleAgentResponse = useCallback((response: AgentResponse) => {
    const msg: Message = {
      id: `agent-${++messageCounter}-${Date.now()}`,
      role: 'agent',
      content: response.content,
      timestamp: Date.now(),
      toolCalls: response.tool_calls,
    };
    setMessages(prev => [...prev, msg]);
    setIsAgentRunning(false);
    setCheckpoint(null);   // final response ends the session

    if (response.tool_calls?.length) {
      response.tool_calls.forEach(tc => {
        addLog('tool_call', `${tc.name} — ${tc.status || 'called'}`, undefined, tc);
      });
    }
    addLog('reasoning', response.content.length > 150 ? response.content.slice(0, 150) + '...' : response.content);
  }, [addLog]);

  // A streamed chat line from the agent (narrative text).
  const handleAgentSay = useCallback((msg: AgentSay) => {
    if (!msg.content || !msg.content.trim()) return;
    setMessages(prev => [...prev, {
      id: `agent-${++messageCounter}-${Date.now()}`,
      role: 'agent',
      content: msg.content,
      timestamp: Date.now(),
    }]);
  }, []);

  // A checkpoint: the agent paused for a decision. Show its narrative as a
  // bubble and surface the options in the right-side panel.
  const handleAgentCheckpoint = useCallback((cp: AgentCheckpoint) => {
    if (cp.agentMessage && cp.agentMessage.trim()) {
      setMessages(prev => [...prev, {
        id: `agent-${++messageCounter}-${Date.now()}`,
        role: 'agent',
        content: cp.agentMessage,
        timestamp: Date.now(),
      }]);
    }
    setCheckpoint({
      agentMessage: cp.agentMessage,
      score: cp.score,
      grade: cp.grade,
      suggestions: cp.suggestions || [],
      rules: cp.rules || [],
      actions: cp.actions || { approve: true, end: true, yes: false },
    });
    setIsAgentRunning(false);
    if (cp.score != null) {
      addLog('info', `Checkpoint — score ${cp.score}/100${cp.grade ? ` (${cp.grade})` : ''}`);
    }
  }, [addLog]);

  const resetChat = useCallback(() => {
    setMessages([]);
    setNodeStatuses({});
    setIsAgentRunning(false);
    setLogEntries([]);
    setCheckpoint(null);
    addLog('info', 'Chat reset');
  }, [addLog]);

  const cancelLast = useCallback(() => {
    setMessages(prev => {
      if (prev.length === 0) return prev;
      const lastUserIdx = prev.reduce((acc, m, i) => m.role === 'user' ? i : acc, -1);
      if (lastUserIdx === -1) return prev;
      return prev.slice(0, lastUserIdx);
    });
    setIsAgentRunning(false);
    addLog('info', 'Last message cancelled');
  }, [addLog]);

  return {
    messages,
    nodeStatuses,
    isAgentRunning,
    logEntries,
    checkpoint,
    addUserMessage,
    beginAwaitingResponse,
    handleAgentEvent,
    handleAgentResponse,
    handleAgentSay,
    handleAgentCheckpoint,
    resetChat,
    cancelLast,
  };
}
