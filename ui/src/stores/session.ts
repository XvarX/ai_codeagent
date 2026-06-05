// ui/src/stores/session.ts
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { agentWs } from '../services/agentWs';

export interface ProjectInfo {
  hash: string;
  path: string;
  name: string;
  last_opened: string;
}

export interface SessionInfo {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  model: string;
  msg_count: number;
  project_path?: string;
  project_name?: string;
}

export const useSessionStore = defineStore('session', () => {
  const projects = ref<ProjectInfo[]>([]);
  const currentProjectPath = ref<string>('');
  const currentProjectName = ref<string>('');
  const sessions = ref<SessionInfo[]>([]);
  const currentSessionId = ref<string>('');

  function setProjects(list: ProjectInfo[]) {
    projects.value = list;
    // Auto-restore last opened project
    if (!currentProjectPath.value && list.length > 0) {
      openProject(list[0].path);
    }
  }

  function setProjectOpened(path: string, sessionList: SessionInfo[]) {
    currentProjectPath.value = path;
    const p = projects.value.find(p => p.path === path);
    currentProjectName.value = p?.name || path.split(/[\\/]/).pop() || '';
    sessions.value = sessionList;
    // Auto-restore last session
    if (!currentSessionId.value && sessionList.length > 0) {
      loadSession(sessionList[0].session_id);
    }
  }

  function setSessionCreated(sessionId: string, title: string) {
    currentSessionId.value = sessionId;
    sessions.value.unshift({
      session_id: sessionId,
      title,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      model: '',
      msg_count: 0,
    });
  }

  function setCurrentSession(sessionId: string) {
    currentSessionId.value = sessionId;
  }

  function openProject(path: string) {
    currentSessionId.value = '';
    agentWs.send({ type: 'open_project', path });
  }

  function createSession(title: string = 'New Chat') {
    agentWs.send({ type: 'create_session', project_path: currentProjectPath.value, title });
  }

  function loadSession(sessionId: string) {
    agentWs.send({ type: 'load_session', project_path: currentProjectPath.value, session_id: sessionId });
  }

  function listProjects() {
    agentWs.send({ type: 'list_projects' });
  }

  function listAllSessions() {
    agentWs.send({ type: 'list_all_sessions' });
  }

  return {
    projects, currentProjectPath, currentProjectName,
    sessions, currentSessionId,
    setProjects, setProjectOpened, setSessionCreated, setCurrentSession,
    openProject, createSession, loadSession, listProjects, listAllSessions,
  };
});
