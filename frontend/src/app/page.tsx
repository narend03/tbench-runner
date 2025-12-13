'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Terminal, Key, RefreshCw, Activity, Zap } from 'lucide-react';
import TaskUpload from '@/components/TaskUpload';
import TaskList from '@/components/TaskList';
import TaskDetail from '@/components/TaskDetail';
import { getTasks, getModels, getAgents, getStats, Task, Model, Agent, Stats } from '@/lib/api';

export default function Home() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [loading, setLoading] = useState(true);

  // Load initial data
  const loadData = async () => {
    try {
      const [tasksData, modelsData, agentsData, statsData] = await Promise.all([
        getTasks(),
        getModels(),
        getAgents(),
        getStats(),
      ]);
      setTasks(tasksData);
      setModels(modelsData);
      setAgents(agentsData);
      setStats(statsData);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    
    // Poll for updates
    const interval = setInterval(() => {
      loadData();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  // Load API key from localStorage
  useEffect(() => {
    const savedKey = localStorage.getItem('openai_api_key');
    if (savedKey) setApiKey(savedKey);
  }, []);

  // Save API key to localStorage
  const handleApiKeyChange = (value: string) => {
    setApiKey(value);
    localStorage.setItem('openai_api_key', value);
  };

  return (
    <div className="min-h-screen bg-terminal-black grid-bg">
      {/* Header */}
      <header className="border-b border-terminal-border bg-terminal-dark/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-terminal-green/20 rounded-lg">
                <Terminal className="w-6 h-6 text-terminal-green" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">TBench Runner</h1>
                <p className="text-sm text-terminal-muted">Terminal-Bench Task Execution Platform</p>
              </div>
            </div>

            {/* Stats */}
            {stats && (
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-terminal-blue" />
                  <span className="text-terminal-muted text-sm">
                    {stats.tasks.running} running
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-terminal-green" />
                  <span className="text-terminal-muted text-sm">
                    {stats.runs.passed}/{stats.runs.total} passed
                  </span>
                </div>
                <button
                  onClick={loadData}
                  className="p-2 text-terminal-muted hover:text-terminal-text transition-colors"
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* API Key Input */}
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 bg-terminal-dark border border-terminal-border rounded-xl p-4"
        >
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-terminal-muted">
              <Key className="w-4 h-4" />
              <span className="text-sm font-medium">OpenAI API Key</span>
            </div>
            <div className="flex-1 relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => handleApiKeyChange(e.target.value)}
                placeholder="sk-..."
                className="w-full bg-terminal-darker border border-terminal-border rounded-lg px-4 py-2 text-terminal-text placeholder-terminal-muted focus:outline-none focus:border-terminal-blue transition-colors font-mono text-sm"
              />
              <button
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-terminal-muted hover:text-terminal-text text-xs"
              >
                {showApiKey ? 'Hide' : 'Show'}
              </button>
            </div>
            <span className="text-xs text-terminal-muted">
              {apiKey ? '✓ Key saved' : 'Required for LLM agents'}
            </span>
          </div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Upload & Task List */}
          <div className="space-y-8">
            {/* Upload Section */}
            {models.length > 0 && agents.length > 0 && (
              <TaskUpload
                models={models}
                agents={agents}
                onTaskCreated={loadData}
              />
            )}

            {/* Task List */}
            <div>
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-terminal-blue" />
                Tasks
                {tasks.length > 0 && (
                  <span className="text-sm text-terminal-muted font-normal">
                    ({tasks.length})
                  </span>
                )}
              </h2>
              <TaskList
                tasks={tasks}
                selectedTaskId={selectedTaskId}
                onSelectTask={setSelectedTaskId}
                onTaskUpdated={loadData}
              />
            </div>
          </div>

          {/* Right Column - Task Detail */}
          <div>
            {selectedTaskId ? (
              <TaskDetail
                taskId={selectedTaskId}
                apiKey={apiKey}
                onUpdate={loadData}
              />
            ) : (
              <div className="bg-terminal-dark border border-terminal-border rounded-xl p-12 text-center">
                <Terminal className="w-12 h-12 text-terminal-muted mx-auto mb-4" />
                <p className="text-terminal-muted">Select a task to view details</p>
                <p className="text-terminal-muted text-sm mt-2">
                  Upload a new task or click on an existing one
                </p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-terminal-border mt-12 py-6">
        <div className="max-w-7xl mx-auto px-6 text-center text-terminal-muted text-sm">
          TBench Runner • Terminal-Bench 2.0 Execution Platform • Harbor Harness
        </div>
      </footer>
    </div>
  );
}
