'use client';

import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileArchive, X, Loader2, Zap, Settings2 } from 'lucide-react';
import { createTask, Model, Agent } from '@/lib/api';

interface TaskUploadProps {
  models: Model[];
  agents: Agent[];
  onTaskCreated: () => void;
}

export default function TaskUpload({ models, agents, onTaskCreated }: TaskUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [taskName, setTaskName] = useState('');
  const [selectedModel, setSelectedModel] = useState(models[0]?.id || 'openai/gpt-4o');
  const [selectedAgent, setSelectedAgent] = useState(agents[0]?.id || 'terminus-2');
  const [numRuns, setNumRuns] = useState(10);
  const [isUploading, setIsUploading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const uploadedFile = acceptedFiles[0];
    if (uploadedFile) {
      setFile(uploadedFile);
      // Auto-generate task name from filename if empty
      if (!taskName) {
        const name = uploadedFile.name.replace(/\.zip$/i, '').replace(/[-_]/g, ' ');
        setTaskName(name);
      }
      setError(null);
    }
  }, [taskName]);

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'application/zip': ['.zip'],
      'application/x-zip-compressed': ['.zip'],
    },
    maxFiles: 1,
    maxSize: 100 * 1024 * 1024, // 100MB
  });

  const selectedAgentData = agents.find(a => a.id === selectedAgent);
  const harness = selectedAgentData?.harness || 'harbor';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!file) {
      setError('Please upload a task file');
      return;
    }
    
    if (!taskName.trim()) {
      setError('Please enter a task name');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      await createTask(file, taskName.trim(), selectedModel, selectedAgent, harness, numRuns);
      
      // Reset form
      setFile(null);
      setTaskName('');
      setNumRuns(10);
      
      onTaskCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload task');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-terminal-dark border border-terminal-border rounded-xl p-6"
    >
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Zap className="w-5 h-5 text-terminal-yellow" />
          New Benchmark Run
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Drop Zone */}
        <div
          {...getRootProps()}
          className={`dropzone p-8 rounded-lg cursor-pointer transition-all text-center ${
            isDragActive ? 'active' : ''
          } ${isDragReject ? 'reject' : ''}`}
        >
          <input {...getInputProps()} />
          
          <AnimatePresence mode="wait">
            {file ? (
              <motion.div
                key="file"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="flex flex-col items-center"
              >
                <FileArchive className="w-12 h-12 text-terminal-green mb-3" />
                <p className="text-terminal-text font-medium">{file.name}</p>
                <p className="text-terminal-muted text-sm mt-1">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                  className="mt-3 text-terminal-red hover:text-red-400 text-sm flex items-center gap-1"
                >
                  <X className="w-4 h-4" />
                  Remove
                </button>
              </motion.div>
            ) : (
              <motion.div
                key="upload"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center"
              >
                <Upload className={`w-12 h-12 mb-3 ${isDragActive ? 'text-terminal-blue' : 'text-terminal-muted'}`} />
                <p className="text-terminal-text">
                  {isDragActive ? 'Drop your task here' : 'Drag & drop your Terminal-Bench task'}
                </p>
                <p className="text-terminal-muted text-sm mt-2">
                  or click to browse (ZIP files only, max 100MB)
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Task Name */}
        <div>
          <label className="block text-sm font-medium text-terminal-muted mb-2">
            Task Name
          </label>
          <input
            type="text"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            placeholder="Enter a name for this task"
            className="w-full bg-terminal-darker border border-terminal-border rounded-lg px-4 py-3 text-terminal-text placeholder-terminal-muted focus:outline-none focus:border-terminal-blue transition-colors"
          />
        </div>

        {/* Model Selection */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-terminal-muted mb-2">
              Model
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full bg-terminal-darker border border-terminal-border rounded-lg px-4 py-3 text-terminal-text focus:outline-none focus:border-terminal-blue transition-colors"
            >
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name} ({model.provider})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-terminal-muted mb-2">
              Agent / Harness
            </label>
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="w-full bg-terminal-darker border border-terminal-border rounded-lg px-4 py-3 text-terminal-text focus:outline-none focus:border-terminal-blue transition-colors"
            >
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Advanced Settings */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-terminal-muted hover:text-terminal-text text-sm transition-colors"
          >
            <Settings2 className="w-4 h-4" />
            {showAdvanced ? 'Hide' : 'Show'} Advanced Settings
          </button>
          
          <AnimatePresence>
            {showAdvanced && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="mt-4 p-4 bg-terminal-darker rounded-lg border border-terminal-border">
                  <div>
                    <label className="block text-sm font-medium text-terminal-muted mb-2">
                      Number of Runs
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={numRuns}
                      onChange={(e) => setNumRuns(parseInt(e.target.value) || 10)}
                      className="w-32 bg-terminal-black border border-terminal-border rounded-lg px-4 py-2 text-terminal-text focus:outline-none focus:border-terminal-blue transition-colors"
                    />
                    <p className="text-terminal-muted text-xs mt-1">
                      Each task will be executed {numRuns} times for statistical significance
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Error Message */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-terminal-red"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isUploading || !file}
          className={`w-full py-4 rounded-lg font-medium text-lg flex items-center justify-center gap-2 transition-all ${
            isUploading || !file
              ? 'bg-terminal-gray text-terminal-muted cursor-not-allowed'
              : 'bg-gradient-to-r from-terminal-green to-terminal-blue hover:opacity-90 text-white'
          }`}
        >
          {isUploading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Starting Benchmark...
            </>
          ) : (
            <>
              <Zap className="w-5 h-5" />
              Start {numRuns} Benchmark Runs
            </>
          )}
        </button>
      </form>
    </motion.div>
  );
}

