import { useState, useCallback, useRef } from 'react';
import type { Message } from '../components/ChatPanel/MessageBubble';
import type { NodeStatus } from '../components/ProcessPanel/ToolStatusCard';
import type { AgentEvent, AgentResponse } from '../utils/wsProtocol';
import type { LogEntry } from '../components/ReasoningLog/ReasoningLog';
import type { ScoreData } from '../components/Dashboard/Dashboard';

const DEMO_PIPELINE_NODES = [
  'profile_agent', 'space_type_agent', 'reason', 'add_objects',
  'collision', 'visibility', 'orientation',
  'path_analysis', 'reachability',
  'scoring', 'checkpoint', 'explain',
];

function generateDemoScores(): ScoreData {
  const rand = (min: number, max: number) => min + Math.random() * (max - min);
  const collision = Math.round(rand(70, 98));
  const visibility = Math.round(rand(60, 95));
  const path = Math.round(rand(65, 92));
  const reachability = Math.round(rand(72, 96));
  const orientation = Math.round(rand(68, 94));
  const weights = { collision: 0.30, visibility: 0.20, path: 0.25, reachability: 0.15, orientation: 0.10 };
  const overall = Math.round(
    collision * weights.collision +
    visibility * weights.visibility +
    path * weights.path +
    reachability * weights.reachability +
    orientation * weights.orientation
  );
  const grade = overall >= 90 ? 'A' : overall >= 80 ? 'B' : overall >= 70 ? 'C' : overall >= 60 ? 'D' : 'F';
  return {
    overall, grade, collision, visibility, path, reachability, orientation, weights,
    histogramData: {
      clearance: Array.from({ length: 20 }, () => Math.round(rand(0.1, 3.0) * 10) / 10),
      pathDistances: Array.from({ length: 20 }, () => Math.round(rand(1, 15) * 10) / 10),
    },
  };
}

export interface UseAgentStateReturn {
  messages: Message[];
  nodeStatuses: Record<string, NodeStatus>;
  isAgentRunning: boolean;
  logEntries: LogEntry[];
  addUserMessage: (content: string) => void;
  handleAgentEvent: (event: AgentEvent) => void;
  handleAgentResponse: (response: AgentResponse) => void;
  runDemoSimulation: (prompt: string) => void;
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
    addLog('info', `User prompt: "${content.length > 80 ? content.slice(0, 80) + '...' : content}"`);
  }, [addLog]);

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

    if (response.tool_calls?.length) {
      response.tool_calls.forEach(tc => {
        addLog('tool_call', `${tc.name} — ${tc.status || 'called'}`, undefined, tc);
      });
    }
    addLog('reasoning', response.content.length > 150 ? response.content.slice(0, 150) + '...' : response.content);
  }, [addLog]);

  const demoRunningRef = useRef(false);
  const onScoresReadyRef = useRef(options?.onScoresReady);
  onScoresReadyRef.current = options?.onScoresReady;

  const runDemoSimulation = useCallback((prompt: string) => {
    if (demoRunningRef.current) return;
    demoRunningRef.current = true;
    setIsAgentRunning(true);

    // Reset all node statuses
    setNodeStatuses({});
    addLog('info', `Demo simulation started for: "${prompt.length > 60 ? prompt.slice(0, 60) + '...' : prompt}"`);

    let i = 0;
    const runNext = () => {
      if (i >= DEMO_PIPELINE_NODES.length) {
        // Final response
        const response: Message = {
          id: `agent-${++messageCounter}-${Date.now()}`,
          role: 'agent',
          content:
            `Demo analysis complete.\n\n` +
            `**Prompt**: "${prompt}"\n\n` +
            `All 12 pipeline nodes ran successfully:\n` +
            `- Profile Agent: identified space requirements\n` +
            `- Space Type Agent: classified zones\n` +
            `- Collision/Visibility/Orientation: spatial checks passed\n` +
            `- Scoring: layout scored 82/100 (B)\n\n` +
            `*This is a frontend demo. Connect the backend for real analysis.*`,
          timestamp: Date.now(),
          toolCalls: [
            { name: 'collision_check', status: 'completed', args: { threshold: 0.3 }, result: 'No collisions' },
            { name: 'scoring', status: 'completed', args: { weights: 'default' }, result: 'Score: 82/100' },
          ],
        };
        setMessages(prev => [...prev, response]);
        setIsAgentRunning(false);
        demoRunningRef.current = false;
        addLog('reasoning', 'Demo simulation complete — all nodes passed');
        return;
      }

      const node = DEMO_PIPELINE_NODES[i];

      // Mark as running
      setNodeStatuses(prev => ({ ...prev, [node]: 'running' }));
      addLog('node_start', 'Started', node);

      // After delay, mark as completed and proceed
      setTimeout(() => {
        setNodeStatuses(prev => ({ ...prev, [node]: 'completed' }));
        addLog('node_complete', `Completed — ${node} analysis finished`, node);

        // Generate scores when the scoring node completes
        if (node === 'scoring' && onScoresReadyRef.current) {
          const scores = generateDemoScores();
          onScoresReadyRef.current(scores);
          addLog('info', `Scores generated: ${scores.overall}/100 (${scores.grade})`);
        }

        i++;
        setTimeout(runNext, 200);
      }, 800 + Math.random() * 600);
    };

    setTimeout(runNext, 300);
  }, [addLog]);

  const resetChat = useCallback(() => {
    setMessages([]);
    setNodeStatuses({});
    setIsAgentRunning(false);
    setLogEntries([]);
    demoRunningRef.current = false;
    addLog('info', 'Chat reset');
  }, [addLog]);

  const cancelLast = useCallback(() => {
    setMessages(prev => {
      if (prev.length === 0) return prev;
      // Remove last user message and any agent response after it
      const lastUserIdx = prev.reduce((acc, m, i) => m.role === 'user' ? i : acc, -1);
      if (lastUserIdx === -1) return prev;
      return prev.slice(0, lastUserIdx);
    });
    setIsAgentRunning(false);
    demoRunningRef.current = false;
    addLog('info', 'Last message cancelled');
  }, [addLog]);

  return {
    messages,
    nodeStatuses,
    isAgentRunning,
    logEntries,
    addUserMessage,
    handleAgentEvent,
    handleAgentResponse,
    runDemoSimulation,
    resetChat,
    cancelLast,
  };
}
