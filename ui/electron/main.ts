import { app, BrowserWindow, dialog, Menu } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;
let restartCount = 0;

const isDev = !app.isPackaged;
const PYTHON_PORT = 18765;

function getPythonExe(): string {
  // In production, use bundled agentcore.exe
  if (!isDev) return path.join(process.resourcesPath!, 'agentcore', 'agentcore.exe');
  return 'python';
}

function startPythonBackend(): void {
  if (pythonProcess) return;

  const pythonCmd = getPythonExe();
  const args = isDev
    ? [path.resolve(__dirname, '..', '..', 'agentcore', 'main.py'), '--ws', '--port', String(PYTHON_PORT)]
    : ['--ws', '--port', String(PYTHON_PORT)];

  console.log(`[electron] Starting backend: ${pythonCmd} ${args.join(' ')}`);
  pythonProcess = spawn(pythonCmd, args);

  pythonProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[python] ${data.toString().trim()}`);
  });

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[python] ${data.toString().trim()}`);
  });

  pythonProcess.on('exit', (code) => {
    pythonProcess = null;
    if (code !== 0 && restartCount < 3) {
      restartCount++;
      console.log(`[electron] Backend exited (code=${code}), restarting (${restartCount}/3)...`);
      setTimeout(startPythonBackend, 2000);
    } else if (code !== 0) {
      dialog.showErrorBox('Backend Error', 'Python backend crashed. Restart the application.');
    }
  });
}

function stopPythonBackend(): void {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => { mainWindow = null; });
}

function buildMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'Agent',
      submenu: [
        {
          label: 'Restart Backend',
          click: () => {
            stopPythonBackend();
            restartCount = 0;
            startPythonBackend();
          },
        },
        { type: 'separator' },
        { label: 'Quit', role: 'quit' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Reload', role: 'reload' },
        { label: 'Toggle DevTools', role: 'toggleDevTools' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  buildMenu();
  startPythonBackend();
  // Wait a bit for backend to start
  setTimeout(createWindow, 1500);
});

app.on('window-all-closed', () => {
  stopPythonBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopPythonBackend();
});
