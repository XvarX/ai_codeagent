use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;
use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};

struct PythonBackend(Mutex<Option<Child>>);

fn get_backend_cmd(app: &tauri::AppHandle) -> Option<(String, Vec<String>)> {
    // Dev mode: always use python + project root, regardless of bundled exe
    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let project_root = manifest_dir.join("..").join("..");
        let data_dir = project_root.join(".ai-code-agent");
        return Some((
            "python".to_string(),
            vec![
                "-m".to_string(),
                "agentcore.main".to_string(),
                "--ws".to_string(),
                "--port".to_string(), "18765".to_string(),
                "--data-dir".to_string(), data_dir.to_string_lossy().to_string(),
            ],
        ));
    }

    // Release mode: use bundled exe + ~/.ai-code-agent
    let resource_dir = app.path().resource_dir().ok()?;
    let bundled_exe = resource_dir.join("agentcore").join("agentcore.exe");

    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .ok()?;
    let data_dir = PathBuf::from(&home).join(".ai-code-agent");

    // Default CWD: last opened project, or home
    let cwd = {
        let projects_json = data_dir.join("store").join("projects.json");
        let last_project = std::fs::read_to_string(&projects_json)
            .ok()
            .and_then(|s| serde_json::from_str::<Vec<serde_json::Value>>(&s).ok())
            .and_then(|list| {
                let mut sorted = list;
                sorted.sort_by(|a, b| {
                    let ta = a.get("last_opened").and_then(|v| v.as_str()).unwrap_or("");
                    let tb = b.get("last_opened").and_then(|v| v.as_str()).unwrap_or("");
                    tb.cmp(ta)
                });
                sorted.first()
                    .and_then(|p| p.get("path"))
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
            })
            .unwrap_or_else(|| home.clone());
        last_project
    };

    Some((
        bundled_exe.to_string_lossy().to_string(),
        vec![
            "--ws".to_string(),
            "--port".to_string(), "18765".to_string(),
            "--data-dir".to_string(), data_dir.to_string_lossy().to_string(),
            "--cwd".to_string(), cwd.to_string(),
        ],
    ))
}

fn start_python(app: &tauri::AppHandle) -> Option<Child> {
    let (cmd, args) = get_backend_cmd(app)?;
    println!("[tauri] Starting backend: {} {:?}", cmd, args);

    let mut command = Command::new(&cmd);
    command.args(&args);

    // In dev mode, run from project root
    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let project_root = manifest_dir.join("..").join("..");
        command.current_dir(project_root);
    }

    match command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("PYTHONUNBUFFERED", "1")
        .spawn()
    {
        Ok(mut child) => {
            let child_stdout = child.stdout.take();
            let child_stderr = child.stderr.take();

            if let Some(stdout) = child_stdout {
                std::thread::spawn(move || {
                    let reader = BufReader::new(stdout);
                    for line in reader.lines() {
                        if let Ok(line) = line {
                            println!("[python] {}", line);
                        }
                    }
                });
            }
            if let Some(stderr) = child_stderr {
                std::thread::spawn(move || {
                    let reader = BufReader::new(stderr);
                    for line in reader.lines() {
                        if let Ok(line) = line {
                            eprintln!("[python] {}", line);
                        }
                    }
                });
            }

            println!("[tauri] Backend started (pid={})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[tauri] Failed to start backend: {}", e);
            None
        }
    }
}

fn kill_python(lock: &Mutex<Option<Child>>) {
    if let Ok(mut guard) = lock.lock() {
        if let Some(mut child) = guard.take() {
            println!("[tauri] Stopping backend...");
            if let Err(e) = child.kill() {
                eprintln!("[tauri] Failed to kill backend: {}", e);
            }
            if let Err(e) = child.wait() {
                eprintln!("[tauri] Failed to wait for backend: {}", e);
            }
        }
    }
}

fn restart_python(app: &tauri::AppHandle) {
    let state = app.state::<PythonBackend>();
    let mut guard = state.0.lock().unwrap();
    if let Some(mut old) = guard.take() {
        println!("[tauri] Stopping backend...");
        let _ = old.kill();
        let _ = old.wait();
    }
    *guard = start_python(app);
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
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
                            w.open_devtools();
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
                kill_python(&state.0);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
