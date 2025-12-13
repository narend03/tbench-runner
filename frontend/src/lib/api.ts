/**
 * API client for TBench Runner backend
 */

import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Types
export interface Model {
  id: string;
  name: string;
  provider: string;
}

export interface Agent {
  id: string;
  name: string;
  harness: string;
}

export interface Task {
  id: number;
  name: string;
  description: string | null;
  original_filename: string;
  model: string;
  agent: string;
  harness: string;
  num_runs: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  total_runs: number;
  passed_runs: number;
  failed_runs: number;
}

export interface Run {
  id: number;
  task_id: number;
  run_number: number;
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'timeout';
  started_at: string | null;
  completed_at: string | null;
  tests_total: number;
  tests_passed: number;
  tests_failed: number;
  logs: string | null;
  error_message: string | null;
  duration_seconds: number | null;
}

export interface TaskDetail extends Task {
  runs: Run[];
}

export interface Stats {
  tasks: {
    total: number;
    pending: number;
    running: number;
    completed: number;
    failed: number;
  };
  runs: {
    total: number;
    passed: number;
    failed: number;
  };
}

// API Functions

export async function getModels(): Promise<Model[]> {
  const response = await api.get<Model[]>('/api/models');
  return response.data;
}

export async function getAgents(): Promise<Agent[]> {
  const response = await api.get<Agent[]>('/api/agents');
  return response.data;
}

export async function getTasks(status?: string): Promise<Task[]> {
  const params = status ? { status } : {};
  const response = await api.get<Task[]>('/api/tasks', { params });
  return response.data;
}

export async function getTask(taskId: number): Promise<TaskDetail> {
  const response = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
  return response.data;
}

export async function createTask(
  file: File,
  name: string,
  model: string,
  agent: string,
  harness: string,
  numRuns: number
): Promise<Task> {
  const formData = new FormData();
  formData.append('file', file);
  
  const params = new URLSearchParams({
    name,
    model,
    agent,
    harness,
    num_runs: numRuns.toString(),
  });
  
  const response = await api.post<Task>(`/api/tasks?${params}`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  
  return response.data;
}

export async function deleteTask(taskId: number): Promise<void> {
  await api.delete(`/api/tasks/${taskId}`);
}

export async function retryTask(taskId: number): Promise<void> {
  await api.post(`/api/tasks/${taskId}/retry`);
}

export async function getRuns(taskId: number): Promise<Run[]> {
  const response = await api.get<Run[]>(`/api/tasks/${taskId}/runs`);
  return response.data;
}

export async function getRun(taskId: number, runId: number): Promise<Run> {
  const response = await api.get<Run>(`/api/tasks/${taskId}/runs/${runId}`);
  return response.data;
}

export async function getRunLogs(taskId: number, runId: number): Promise<{ logs: string; error_message: string | null }> {
  const response = await api.get(`/api/tasks/${taskId}/runs/${runId}/logs`);
  return response.data;
}

export async function getStats(): Promise<Stats> {
  const response = await api.get<Stats>('/api/stats');
  return response.data;
}

// Stage 4: Async execution
export async function executeTaskAsync(
  taskId: number,
  openaiApiKey: string,
  timeoutSeconds: number = 1200
): Promise<{ message: string; task_id: number; runs_queued: number; status: string; poll_url: string }> {
  const params = new URLSearchParams({
    openrouter_api_key: openaiApiKey,
    timeout_seconds: timeoutSeconds.toString(),
  });
  const response = await api.post(`/api/tasks/${taskId}/execute-async?${params}`);
  return response.data;
}

export async function startTask(taskId: number): Promise<{ message: string; task_id: number }> {
  const response = await api.post(`/api/tasks/${taskId}/start`);
  return response.data;
}

export default api;

