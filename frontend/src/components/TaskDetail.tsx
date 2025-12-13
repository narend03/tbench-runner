'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle, XCircle, Clock, Loader2, AlertCircle,
  Play, Terminal, ChevronDown, ChevronUp, Copy, Check,
  Zap, Timer, TestTube
} from 'lucide-react';
import { TaskDetail as TaskDetailType, getTask, executeTaskAsync, getRunLogs } from '@/lib/api';

interface TaskDetailProps {
  taskId: number;
  apiKey: string;
  onUpdate: () => void;
}

const runStatusConfig: Record<string, { icon: typeof Clock; color: string; bg: string; label: string; animate?: boolean }> = {
  pending: { icon: Clock, color: 'text-terminal-yellow', bg: 'bg-yellow-500/20', label: 'Pending' },
  running: { icon: Loader2, color: 'text-terminal-blue', bg: 'bg-blue-500/20', label: 'Running', animate: true },
  passed: { icon: CheckCircle, color: 'text-terminal-green', bg: 'bg-green-500/20', label: 'Passed' },
  failed: { icon: XCircle, color: 'text-terminal-red', bg: 'bg-red-500/20', label: 'Failed' },
  error: { icon: AlertCircle, color: 'text-terminal-red', bg: 'bg-red-500/20', label: 'Error' },
  timeout: { icon: Timer, color: 'text-terminal-yellow', bg: 'bg-yellow-500/20', label: 'Timeout' },
};

export default function TaskDetail({ taskId, apiKey, onUpdate }: TaskDetailProps) {
  const [task, setTask] = useState<TaskDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [expandedRun, setExpandedRun] = useState<number | null>(null);
  const [runLogs, setRunLogs] = useState<Record<number, string>>({});
  const [copied, setCopied] = useState(false);

  // Fetch task details
  const fetchTask = useCallback(async () => {
    try {
      const data = await getTask(taskId);
      setTask(data);
    } catch (error) {
      console.error('Failed to fetch task:', error);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  // Poll for updates when running
  useEffect(() => {
    fetchTask();
    
    const interval = setInterval(() => {
      if (task?.status === 'running') {
        fetchTask();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [taskId, task?.status, fetchTask]);

  // Fetch logs when run is expanded
  const handleExpandRun = async (runId: number) => {
    if (expandedRun === runId) {
      setExpandedRun(null);
      return;
    }
    
    setExpandedRun(runId);
    
    if (!runLogs[runId]) {
      try {
        const { logs } = await getRunLogs(taskId, runId);
        setRunLogs(prev => ({ ...prev, [runId]: logs || 'No logs available' }));
      } catch {
        setRunLogs(prev => ({ ...prev, [runId]: 'Failed to load logs' }));
      }
    }
  };

  // Execute task
  const handleExecute = async () => {
    if (!apiKey) {
      alert('Please enter an OpenAI API key');
      return;
    }

    setExecuting(true);
    try {
      await executeTaskAsync(taskId, apiKey);
      fetchTask();
      onUpdate();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      alert(err.response?.data?.detail || 'Failed to execute task');
    } finally {
      setExecuting(false);
    }
  };

  // Copy logs
  const handleCopyLogs = (logs: string) => {
    navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="bg-terminal-dark border border-terminal-border rounded-xl p-8 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-terminal-blue animate-spin" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="bg-terminal-dark border border-terminal-border rounded-xl p-8 text-center">
        <p className="text-terminal-muted">Task not found</p>
      </div>
    );
  }

  const passRate = task.total_runs > 0 
    ? Math.round((task.passed_runs / task.total_runs) * 100) 
    : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-terminal-dark border border-terminal-border rounded-xl overflow-hidden"
    >
      {/* Header */}
      <div className="p-6 border-b border-terminal-border">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">{task.name}</h2>
            <p className="text-terminal-muted mt-1">
              {task.model} • {task.agent} • {task.num_runs} runs
            </p>
          </div>
          
          {task.status === 'pending' && (
            <button
              onClick={handleExecute}
              disabled={executing}
              className="flex items-center gap-2 px-4 py-2 bg-terminal-green hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {executing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {executing ? 'Starting...' : 'Execute'}
            </button>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mt-6">
          <div className="bg-terminal-darker rounded-lg p-4">
            <div className="flex items-center gap-2 text-terminal-muted text-sm mb-1">
              <TestTube className="w-4 h-4" />
              Total Runs
            </div>
            <div className="text-2xl font-bold text-white">{task.total_runs || task.num_runs}</div>
          </div>
          
          <div className="bg-terminal-darker rounded-lg p-4">
            <div className="flex items-center gap-2 text-terminal-green text-sm mb-1">
              <CheckCircle className="w-4 h-4" />
              Passed
            </div>
            <div className="text-2xl font-bold text-terminal-green">{task.passed_runs}</div>
          </div>
          
          <div className="bg-terminal-darker rounded-lg p-4">
            <div className="flex items-center gap-2 text-terminal-red text-sm mb-1">
              <XCircle className="w-4 h-4" />
              Failed
            </div>
            <div className="text-2xl font-bold text-terminal-red">{task.failed_runs}</div>
          </div>
          
          <div className="bg-terminal-darker rounded-lg p-4">
            <div className="flex items-center gap-2 text-terminal-blue text-sm mb-1">
              <Zap className="w-4 h-4" />
              Pass Rate
            </div>
            <div className={`text-2xl font-bold ${
              passRate >= 80 ? 'text-terminal-green' :
              passRate >= 50 ? 'text-terminal-yellow' : 'text-terminal-red'
            }`}>
              {passRate}%
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        {task.status === 'running' && (
          <div className="mt-4">
            <div className="flex justify-between text-sm text-terminal-muted mb-2">
              <span>Progress</span>
              <span>{task.passed_runs + task.failed_runs} / {task.total_runs}</span>
            </div>
            <div className="h-2 bg-terminal-darker rounded-full overflow-hidden">
              <div 
                className="h-full bg-terminal-green progress-bar-animate transition-all duration-500"
                style={{ width: `${((task.passed_runs + task.failed_runs) / task.total_runs) * 100}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Runs List */}
      <div className="p-6">
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Terminal className="w-5 h-5 text-terminal-blue" />
          Run Results
        </h3>

        <div className="space-y-2">
          <AnimatePresence>
            {task.runs.map((run) => {
              const status = runStatusConfig[run.status];
              const StatusIcon = status.icon;
              const isExpanded = expandedRun === run.id;

              return (
                <motion.div
                  key={run.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-terminal-darker rounded-lg overflow-hidden"
                >
                  <button
                    onClick={() => handleExpandRun(run.id)}
                    className="w-full p-4 flex items-center justify-between hover:bg-terminal-gray/30 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className={`p-2 rounded-lg ${status.bg}`}>
                        <StatusIcon 
                          className={`w-4 h-4 ${status.color} ${status.animate ? 'animate-spin' : ''}`} 
                        />
                      </div>
                      <div className="text-left">
                        <span className="text-terminal-text font-medium">Run #{run.run_number}</span>
                        <div className="flex items-center gap-3 text-sm text-terminal-muted mt-0.5">
                          <span className={status.color}>{status.label}</span>
                          {run.duration_seconds && (
                            <>
                              <span>•</span>
                              <span>{run.duration_seconds.toFixed(1)}s</span>
                            </>
                          )}
                          {run.tests_total > 0 && (
                            <>
                              <span>•</span>
                              <span className="text-terminal-green">{run.tests_passed}/{run.tests_total} tests</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    {isExpanded ? (
                      <ChevronUp className="w-5 h-5 text-terminal-muted" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-terminal-muted" />
                    )}
                  </button>

                  {/* Expanded Logs */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="p-4 border-t border-terminal-border">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm text-terminal-muted">Execution Logs</span>
                            <button
                              onClick={() => handleCopyLogs(runLogs[run.id] || '')}
                              className="flex items-center gap-1 text-xs text-terminal-muted hover:text-terminal-text transition-colors"
                            >
                              {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                              {copied ? 'Copied!' : 'Copy'}
                            </button>
                          </div>
                          <div className="log-viewer max-h-96 overflow-y-auto">
                            {runLogs[run.id] || (
                              <div className="flex items-center gap-2 text-terminal-muted">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Loading logs...
                              </div>
                            )}
                          </div>
                          {run.error_message && (
                            <div className="mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                              <p className="text-terminal-red text-sm">{run.error_message}</p>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </AnimatePresence>

          {task.runs.length === 0 && (
            <div className="text-center py-8 text-terminal-muted">
              <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>No runs yet. Click Execute to start.</p>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

