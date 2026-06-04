# Tauri Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Electron with Tauri v2 as the desktop shell, keeping Vue frontend and Python backend unchanged.

**Architecture:** Tauri (Rust) replaces Electron (Node.js) as the outer shell. The Rust side spawns the Python backend as a child process and opens a native WebView2 window loading the Vue app. The Vue app communicates with the Python backend via WebSocket — no Tauri IPC needed.

**Tech Stack:** Rust (tauri v2), Vue 3 + Vite, Python (PyInstaller)

---

## File Map

| File | Responsibility |
|------|---------------|
| `ui/src-tauri/Cargo.toml` | Rust dependencies (tauri v2) |
| `ui/src-tauri/src/main.rs` | Python process lifecycle, window, native menu |
| `ui/src-tauri/tauri.conf.json` | Window/bundle/build config |
| `ui/src-tauri/capabilities/default.json` | Tauri v2 permissions (minimal) |
| `ui/package.json` (modify) | Remove electron deps, add @tauri-apps/cli |
| `build.bat` (modify) | Replace electron:build with tauri build |
| `.gitignore` (modify) | Remove dist-electron/, add src-tauri/target/ |
| `ui/electron/main.ts` (delete) | Replaced by Tauri Rust |
| `ui/tsconfig.electron.json` (delete) | No longer needed |

---

### Task 1: Remove Electron Files

**Files:**
- Delete: `ui/electron/main.ts`
- Delete: `ui/tsconfig.electron.json`

- [ ] **Step 1: Delete Electron source files**

```bash
rm -rf ui/electron
rm ui/tsconfig.electron.json
```

- [ ] **Step 2: Verify deletion**

```bash
ls ui/electron 2>&1 | grep "No such file"
ls ui/tsconfig.electron.json 2>&1 | grep "No such file"
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove Electron files (main.ts, tsconfig.electron.json)"
```

---

### Task 2: Scaffold Tauri Project Structure

**Files:**
- Create: `ui/src-tauri/` directory tree

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p ui/src-tauri/src
mkdir -p ui/src-tauri/capabilities
mkdir -p ui/src-tauri/icons
```

- [ ] **Step 2: Verify structure**

```bash
ls -la ui/src-tauri/
# Expected: src/, capabilities/, icons/
```

---

### Task 3: Write Cargo.toml

**Files:**
- Create: `ui/src-tauri/Cargo.toml`

- [ ] **Step 1: Write Cargo.toml**

```toml
[package]
name = "ai-code-agent"
version = "0.1.0"
edition = "2021"

[dependencies]
tauri = { version = "2", features = [] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"

[build-dependencies]
tauri-build = { version = "2", features = [] }
```

---

### Task 4: Write Tauri Configuration

**Files:**
- Create: `ui/src-tauri/tauri.conf.json`

- [ ] **Step 1: Write tauri.conf.json**

```json
{
  "$schema": "https://raw.githubusercontent.com/tauri-apps/tauri/dev/crates/tauri-config-schema/schema.json",
  "productName": "AI Code Agent",
  "version": "0.1.0",
  "identifier": "com.ai-codeagent.app",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build"
  },
  "app": {
    "windows": [
      {
        "title": "AI Code Agent",
        "width": 1200,
        "height": 800
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "resources": {
      "../../build/agentcore/*": "agentcore/"
    }
  }
}
```

**Note:** Icon files in `icons/` will use Tauri's default placeholder icons. `bundle.resources` maps PyInstaller output into the Tauri bundle at runtime.

---

### Task 5: Write Capabilities Config

**Files:**
- Create: `ui/src-tauri/capabilities/default.json`

- [ ] **Step 1: Write capabilities/default.json**

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capabilities",
  "windows": ["main"],
  "permissions": [
    "core:default"
  ]
}
```

Minimal permissions — the Vue app communicates via WebSocket, not Tauri IPC.

---

### Task 6: Write Tauri Rust Backend

**Files:**
- Create: `ui/src-tauri/src/main.rs`

- [ ] **Step 1: Write main.rs**

```rust
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;
use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};

struct PythonBackend(Mutex<Option<Child>>);

fn get_backend_cmd(app: &tauri::AppHandle) -> (String, Vec<String>) {
    let resource_dir = app.path().resource_dir().unwrap();
    let bundled_exe = resource_dir.join("agentcore").join("agentcore.exe");

    if bundled_exe.exists() {
        return (
            bundled_exe.to_string_lossy().to_string(),
            vec!["--ws".to_string(), "--port".to_string(), "18765".to_string()],
        );
    }

    // Dev mode: resolve python + main.py relative to Cargo manifest
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let main_py = manifest_dir
        .join("..")
        .join("..")
        .join("agentcore")
        .join("main.py");
    (
        "python".to_string(),
        vec![
            main_py.to_string_lossy().to_string(),
            "--ws".to_string(),
            "--port".to_string(),
            "18765".to_string(),
        ],
    )
}

fn start_python(app: &tauri::AppHandle) -> Option<Child> {
    let (cmd, args) = get_backend_cmd(app);
    println!("[tauri] Starting backend: {} {:?}", cmd, args);

    match Command::new(&cmd).args(&args).spawn() {
        Ok(child) => {
            println!("[tauri] Backend started (pid={})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[tauri] Failed to start backend: {}", e);
            None
        }
    }
}

fn kill_python(state: &PythonBackend) {
    if let Some(mut child) = state.0.lock().unwrap().take() {
        println!("[tauri] Stopping backend...");
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn restart_python(app: &tauri::AppHandle) {
    let state = app.state::<PythonBackend>();
    kill_python(&state);
    let child = start_python(app);
    *state.0.lock().unwrap() = child;
}

fn main() {
    tauri::Builder::default()
        .manage(PythonBackend(Mutex::new(None)))
        .setup(|app| {
            // Build native menu
            let restart_item = MenuItemBuilder::with_id("restart", "Restart Backend")
                .build(app)?;
            let quit_item = MenuItemBuilder::with_id("quit", "Quit")
                .build(app)?;
            let agent_menu = SubmenuBuilder::new(app, "Agent")
                .item(&restart_item)
                .separator()
                .item(&quit_item)
                .build()?;

            let reload_item = MenuItemBuilder::with_id("reload", "Reload")
                .build(app)?;
            let devtools_item = MenuItemBuilder::with_id("devtools", "Toggle DevTools")
                .build(app)?;
            let view_menu = SubmenuBuilder::new(app, "View")
                .item(&reload_item)
                .item(&devtools_item)
                .build()?;

            let menu = MenuBuilder::new(app)
                .item(&agent_menu)
                .item(&view_menu)
                .build()?;
            app.set_menu(menu)?;

            // Handle menu events
            app.on_menu_event(|app, event| {
                match event.id().as_ref() {
                    "restart" => restart_python(app),
                    "quit" => app.exit(0),
                    "reload" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.eval("location.reload()");
                        }
                    }
                    "devtools" => {
                        if let Some(w) = app.get_webview_window("main") {
                            if w.is_devtools_open() {
                                w.close_devtools();
                            } else {
                                w.open_devtools();
                            }
                        }
                    }
                    _ => {}
                }
            });

            // Start Python backend
            let child = start_python(app.handle());
            let state = app.state::<PythonBackend>();
            *state.0.lock().unwrap() = child;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<PythonBackend>();
                kill_python(&state);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 2: Create build.rs (required by Tauri)**

```bash
# Create ui/src-tauri/build.rs
```

Write `ui/src-tauri/build.rs`:

```rust
fn main() {
    tauri_build::build()
}
```

---

### Task 7: Update package.json

**Files:**
- Modify: `ui/package.json`

- [ ] **Step 1: Remove Electron dependencies, add Tauri CLI**

Remove from `devDependencies`:
- `"electron": "^42.3.2"`
- `"electron-builder": "^26.8.1"`
- `"concurrently": "^10.0.3"`
- `"wait-on": "^9.0.10"`

Add to `devDependencies`:
- `"@tauri-apps/cli": "^2"`

Remove the `"main"` field: `"main": "dist-electron/main.js"`
Remove the `"build"` key (entire electron-builder config object).

Replace scripts:
- Remove: `"electron:dev": "..."`
- Remove: `"electron:build": "..."`
- Add: `"tauri": "tauri"`

Final `package.json`:

```json
{
  "name": "ui",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "tauri": "tauri"
  },
  "dependencies": {
    "marked": "^18.0.4",
    "pinia": "^3.0.4",
    "vue": "^3.5.34"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2",
    "@types/diff": "^7.0.2",
    "@vitejs/plugin-vue": "^6.0.6",
    "@vue/tsconfig": "^0.9.1",
    "diff": "^9.0.0",
    "typescript": "~6.0.2",
    "vite": "^8.0.12",
    "vue-tsc": "^3.2.8"
  }
}
```

---

### Task 8: Update build.bat

**Files:**
- Modify: `build.bat`

- [ ] **Step 1: Replace Electron build step with Tauri**

Replace lines 17-25 (the Electron build section):

**Old:**
```bat
echo [2/2] Building Electron app...
cd ui
call npm run electron:build
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Electron build failed
    exit /b 1
)
cd ..
echo   -^> build\electron-release\ OK
```

**New:**
```bat
echo [2/2] Building Tauri app...
cd ui
call npm run tauri build
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Tauri build failed
    exit /b 1
)
cd ..
echo   -^> src-tauri\target\release\ OK
```

Also update line 31: `echo   Installer : build\electron-release\` → `echo   Installer : ui\src-tauri\target\release\`

---

### Task 9: Update .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Remove dist-electron entry, add Tauri build artifacts**

Remove line: `dist-electron/`

Add lines:
```
# Tauri
src-tauri/target/
```

---

### Task 10: Install Dependencies and Verify Build

- [ ] **Step 1: Install Rust toolchain (if not present)**

```bash
rustup --version || echo "Install Rust from https://rustup.rs/"
```

If Rust is not installed, the user must install it first. On Windows, ensure the MSVC toolchain:

```bash
rustup default stable-msvc
```

- [ ] **Step 2: Install npm dependencies**

```bash
cd ui
npm install
```

Expected: `@tauri-apps/cli` installed, electron packages removed from node_modules.
Actual node_modules cleanup of old electron packages can be handled by `npm prune` if needed.

- [ ] **Step 3: Verify Tauri CLI works**

```bash
cd ui
npx tauri --version
```

Expected: prints Tauri CLI version (v2.x).

- [ ] **Step 4: Verify Rust compilation (check only)**

```bash
cd ui/src-tauri
cargo check
```

Expected: `Finished` with no errors.

- [ ] **Step 5: Test full Tauri build**

From project root:

```bash
cd ui
npx tauri build
```

Expected: Builds Vite frontend, compiles Rust, produces `.msi` or `.exe` installer in `ui/src-tauri/target/release/bundle/`.

- [ ] **Step 6: Verify build output size**

```bash
du -sh ui/src-tauri/target/release/ai-code-agent.exe
```

Expected: ~5-10MB (vs ~150MB Electron bundle).

---

### Task 11: End-to-End Smoke Test

- [ ] **Step 1: Build Python backend**

```bash
pyinstaller agentcore.spec --distpath build --workpath build/pyinstaller-tmp --noconfirm
```

- [ ] **Step 2: Build Tauri app**

```bash
cd ui
npm run tauri build
```

- [ ] **Step 3: Run the packaged app**

Launch `ui/src-tauri/target/release/ai-code-agent.exe` (or the installer in `bundle/`).

Verify:
- App window opens (1200×800, title "AI Code Agent")
- Python backend starts (check Task Manager for `agentcore.exe` child process)
- Vue frontend loads and connects to WebSocket
- Agent menu: Restart Backend kills + respawns backend
- View menu: Reload refreshes the page
- Closing the window kills the Python child process

- [ ] **Step 4: Verify one-click build.bat**

```bash
build.bat
```

Expected: Both PyInstaller and Tauri build succeed.

---

### Task 12: Commit

- [ ] **Step 1: Stage and commit all changes**

```bash
git add -A
git commit -m "feat: migrate from Electron to Tauri v2 for desktop shell"
```

Ensure commit includes:
- Deleted: `ui/electron/main.ts`, `ui/tsconfig.electron.json`
- Created: `ui/src-tauri/Cargo.toml`, `ui/src-tauri/src/main.rs`, `ui/src-tauri/build.rs`, `ui/src-tauri/tauri.conf.json`, `ui/src-tauri/capabilities/default.json`
- Modified: `ui/package.json`, `build.bat`, `.gitignore`
