// ui/src/stores/session.ts
import { ref, computed } from 'vue';
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

export interface OpenProject {
  path: string;
  name: string;
  sessions: SessionInfo[];
  expanded: boolean;
}

export const useSessionStore = defineStore('session', () => {
  const projects = ref<ProjectInfo[]>([]);
  const currentProjectPath = ref<string>('');
  const currentProjectName = ref<string>('');
  const currentSessionId = ref<string>('');
  const sessionStatuses = ref<Record<string, string>>({});
  const openProjects = ref<OpenProject[]>([]);

  // Derived: sessions of the current project — single source of truth
  const sessions = computed<SessionInfo[]>(() => {
    const op = openProjects.value.find(op => op.path === currentProjectPath.value);
    return op ? op.sessions : [];
  });

  // ── Project helpers ──────────────────────────────

  function _currentOpenProject(): OpenProject | undefined {
    return openProjects.value.find(op => op.path === currentProjectPath.value);
  }

  function _findSessionProject(sessionId: string): OpenProject | undefined {
    return openProjects.value.find(op => op.sessions.some(s => s.session_id === sessionId));
  }

  // ── Event handlers (called from App.vue) ─────────

  function setProjects(list: ProjectInfo[], defaultCwd?: string) {
    projects.value = list;
    if (!currentProjectPath.value) {
      if (list.length > 0) {
        openProject(list[0].path);
      } else if (defaultCwd) {
        openProject(defaultCwd);
      }
    }
  }

  function setProjectOpened(path: string, sessionList: SessionInfo[]) {
    currentProjectPath.value = path;
    const p = projects.value.find(p => p.path === path);
    const name = p?.name || path.split(/[\\/]/).pop() || '';
    currentProjectName.value = name;

    const existing = openProjects.value.find(op => op.path === path);
    if (existing) {
      existing.sessions = sessionList;
      existing.name = name;
      existing.expanded = true;
    } else {
      openProjects.value.push({ path, name, sessions: sessionList, expanded: true });
    }

    if (sessionList.length > 0) {
      loadSession(sessionList[0].session_id);
    } else {
      createSession();
    }
  }

  function setSessionCreated(sessionId: string, title: string) {
    currentSessionId.value = sessionId;
    const info: SessionInfo = {
      session_id: sessionId,
      title,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      model: '',
      msg_count: 0,
    };
    // Only mutate openProjects — sessions is derived
    const op = _currentOpenProject();
    if (op) {
      op.sessions.unshift(info);
    }
  }

  function setCurrentSession(sessionId: string) {
    currentSessionId.value = sessionId;
    // Sync currentProjectPath to match the session's owner
    const op = _findSessionProject(sessionId);
    if (op) {
      currentProjectPath.value = op.path;
      currentProjectName.value = op.name;
    }
  }

  // ── User actions ─────────────────────────────────

  function openProject(path: string) {
    const alreadyOpen = openProjects.value.find(op => op.path === path);
    if (alreadyOpen) {
      currentProjectPath.value = path;
      currentProjectName.value = alreadyOpen.name;
      alreadyOpen.expanded = true;
      if (alreadyOpen.sessions.length > 0) {
        loadSession(alreadyOpen.sessions[0].session_id);
      }
      return;
    }
    currentSessionId.value = '';
    agentWs.send({ type: 'open_project', path });
  }

  function closeProject(path: string) {
    const idx = openProjects.value.findIndex(op => op.path === path);
    if (idx < 0) return;
    for (const s of openProjects.value[idx].sessions) {
      agentWs.send({ type: 'destroy_session', session_id: s.session_id });
    }
    openProjects.value.splice(idx, 1);
    if (currentProjectPath.value === path) {
      if (openProjects.value.length > 0) {
        const next = openProjects.value[0];
        currentProjectPath.value = next.path;
        currentProjectName.value = next.name;
      } else {
        currentProjectPath.value = '';
        currentProjectName.value = '';
        currentSessionId.value = '';
      }
    }
  }

  function deleteProject(path: string) {
    closeProject(path);
    agentWs.send({ type: 'delete_project', project_path: path });
    projects.value = projects.value.filter(p => p.path !== path);
  }

  function closeSession(sessionId: string) {
    agentWs.send({ type: 'destroy_session', session_id: sessionId });
    _removeSessionFromOpenProjects(sessionId);
    delete sessionStatuses.value[sessionId];
  }

  function deleteSession(sessionId: string) {
    const op = _findSessionProject(sessionId);
    if (op) {
      agentWs.send({ type: 'delete_session', project_path: op.path, session_id: sessionId });
      const idx = op.sessions.findIndex(s => s.session_id === sessionId);
      if (idx >= 0) op.sessions.splice(idx, 1);
    }
    delete sessionStatuses.value[sessionId];
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

  function switchSession(id: string) {
    if (id === currentSessionId.value) return;
    agentWs.send({ type: 'switch_session', session_id: id });
  }

  function switchToSession(projectPath: string, sessionId: string) {
    if (sessionId === currentSessionId.value) return;
    // Immediately update UI so it feels responsive
    currentSessionId.value = sessionId;
    currentProjectPath.value = projectPath;
    const op = openProjects.value.find(op => op.path === projectPath);
    if (op) {
      currentProjectName.value = op.name;
    }
    loadSession(sessionId);
  }

  function setSessionStatus(sessionId: string, status: string) {
    sessionStatuses.value[sessionId] = status;
  }

  function removeSession(sessionId: string) {
    _removeSessionFromOpenProjects(sessionId);
    delete sessionStatuses.value[sessionId];
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = '';
    }
  }

  function toggleProjectExpand(path: string) {
    const op = openProjects.value.find(op => op.path === path);
    if (op) op.expanded = !op.expanded;
  }

  // ── Internal ─────────────────────────────────────

  function _removeSessionFromOpenProjects(sessionId: string) {
    for (const op of openProjects.value) {
      const idx = op.sessions.findIndex(s => s.session_id === sessionId);
      if (idx >= 0) {
        op.sessions.splice(idx, 1);
        return;
      }
    }
  }

  return {
    projects, currentProjectPath, currentProjectName,
    sessions, currentSessionId, sessionStatuses,
    openProjects,
    setProjects, setProjectOpened, setSessionCreated, setCurrentSession,
    openProject, closeProject, deleteProject,
    createSession, loadSession, switchSession, switchToSession,
    closeSession, deleteSession,
    setSessionStatus, removeSession,
    listProjects, listAllSessions,
    toggleProjectExpand,
  };
});
