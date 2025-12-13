'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  CheckCircle, XCircle, Clock, Loader2, AlertCircle, 
  ChevronRight, Trash2, RotateCcw, FileArchive 
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Task, deleteTask, retryTask } from '@/lib/api';

interface TaskListProps {
  tasks: Task[];
  selectedTaskId: number | null;
  onSelectTask: (taskId: number) => void;
  onTaskUpdated: () => void;
}

const statusConfig = {
  pending: {
    icon: Clock,
    color: 'text-terminal-yellow',
    bg: 'bg-yellow-500/10',
    label: 'Pending',
  },
  running: {
    icon: Loader2,
    color: 'text-terminal-blue',
    bg: 'bg-blue-500/10',
    label: 'Running',
    animate: true,
  },
  completed: {
    icon: CheckCircle,
    color: 'text-terminal-green',
    bg: 'bg-green-500/10',
    label: 'Completed',
  },
  failed: {
    icon: XCircle,
    color: 'text-terminal-red',
    bg: 'bg-red-500/10',
    label: 'Failed',
  },
  cancelled: {
    icon: AlertCircle,
    color: 'text-terminal-muted',
    bg: 'bg-gray-500/10',
    label: 'Cancelled',
  },
};

export default function TaskList({ tasks, selectedTaskId, onSelectTask, onTaskUpdated }: TaskListProps) {
  const handleDelete = async (e: React.MouseEvent, taskId: number) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this task?')) {
      try {
        await deleteTask(taskId);
        onTaskUpdated();
      } catch (error) {
        console.error('Failed to delete task:', error);
      }
    }
  };

  const handleRetry = async (e: React.MouseEvent, taskId: number) => {
    e.stopPropagation();
    try {
      await retryTask(taskId);
      onTaskUpdated();
    } catch (error) {
      console.error('Failed to retry task:', error);
    }
  };

  if (tasks.length === 0) {
    return (
      <div className="bg-terminal-dark border border-terminal-border rounded-xl p-8 text-center">
        <FileArchive className="w-12 h-12 text-terminal-muted mx-auto mb-4" />
        <p className="text-terminal-muted">No tasks yet</p>
        <p className="text-terminal-muted text-sm mt-1">Upload a Terminal-Bench task to get started</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <AnimatePresence>
        {tasks.map((task, index) => {
          const status = statusConfig[task.status];
          const StatusIcon = status.icon;
          const isSelected = task.id === selectedTaskId;
          const passRate = task.total_runs > 0 
            ? Math.round((task.passed_runs / task.total_runs) * 100) 
            : 0;

          return (
            <motion.div
              key={task.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => onSelectTask(task.id)}
              className={`bg-terminal-dark border rounded-xl p-4 cursor-pointer card-hover ${
                isSelected 
                  ? 'border-terminal-blue glow-border' 
                  : 'border-terminal-border hover:border-terminal-muted'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {/* Status Icon */}
                  <div className={`p-2 rounded-lg ${status.bg}`}>
                    <StatusIcon 
                      className={`w-5 h-5 ${status.color} ${status.animate ? 'animate-spin' : ''}`} 
                    />
                  </div>

                  {/* Task Info */}
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-terminal-text truncate">
                      {task.name}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-sm text-terminal-muted">
                      <span>{task.model.split('/')[1] || task.model}</span>
                      <span>•</span>
                      <span>{task.agent}</span>
                      <span>•</span>
                      <span>{formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}</span>
                    </div>
                  </div>
                </div>

                {/* Progress/Results */}
                <div className="flex items-center gap-4">
                  {/* Run Progress */}
                  {task.status === 'running' || task.status === 'completed' ? (
                    <div className="text-right">
                      <div className="flex items-center gap-2">
                        <span className="text-terminal-green font-mono text-sm">
                          {task.passed_runs}/{task.total_runs || task.num_runs}
                        </span>
                        <span className="text-terminal-muted text-xs">passed</span>
                      </div>
                      {task.total_runs > 0 && (
                        <div className="w-24 h-1.5 bg-terminal-darker rounded-full mt-1 overflow-hidden">
                          <div 
                            className={`h-full rounded-full ${
                              passRate >= 80 ? 'bg-terminal-green' :
                              passRate >= 50 ? 'bg-terminal-yellow' : 'bg-terminal-red'
                            } ${task.status === 'running' ? 'progress-bar-animate' : ''}`}
                            style={{ width: `${passRate}%` }}
                          />
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className={`text-sm ${status.color}`}>{status.label}</span>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {(task.status === 'completed' || task.status === 'failed') && (
                      <button
                        onClick={(e) => handleRetry(e, task.id)}
                        className="p-2 text-terminal-muted hover:text-terminal-blue transition-colors"
                        title="Retry task"
                      >
                        <RotateCcw className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      onClick={(e) => handleDelete(e, task.id)}
                      className="p-2 text-terminal-muted hover:text-terminal-red transition-colors"
                      title="Delete task"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    <ChevronRight className={`w-5 h-5 transition-transform ${
                      isSelected ? 'text-terminal-blue rotate-90' : 'text-terminal-muted'
                    }`} />
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

