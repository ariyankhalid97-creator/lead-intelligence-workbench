const {
  app,
  BrowserWindow,
  ipcMain,
  shell,
  screen,
  dialog,
} = require("electron");
const { autoUpdater } = require("electron-updater");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

app.setName("Lead Extractor");

const ROOT = app.isPackaged
  ? path.join(process.resourcesPath, "backend")
  : path.resolve(__dirname, "..");
const configuredPort = Number(process.env.LEAD_EXTRACTOR_PORT || 8788);
const DASHBOARD_PORT =
  Number.isInteger(configuredPort) &&
  configuredPort >= 1024 &&
  configuredPort <= 65535
    ? configuredPort
    : 8788;
const DASHBOARD_URL = `http://127.0.0.1:${DASHBOARD_PORT}/`;
let mainWindow = null;
let startupWindow = null;
let backend = null;
let saveTimer = null;
let maintenanceState = {
  currentVersion: app.getVersion(),
  status: "idle",
  message: "Ready to check GitHub releases.",
  updateAvailable: false,
  downloaded: false,
  latestVersion: "",
  progress: 0,
};

autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = true;
autoUpdater.allowPrerelease = false;

function dataRoot() {
  return app.isPackaged ? app.getPath("userData") : ROOT;
}
function windowStatePath() {
  return path.join(dataRoot(), "data", "electron-window.json");
}
function runtimePython() {
  return path.join(
    app.getPath("userData"),
    "runtime",
    ".venv",
    "Scripts",
    "python.exe",
  );
}
function backupPython() {
  return app.isPackaged
    ? runtimePython()
    : path.join(ROOT, ".venv", "Scripts", "python.exe");
}
function installerPreferences() {
  try {
    return JSON.parse(
      fs.readFileSync(
        path.join(app.getPath("userData"), "installer-preferences.json"),
        "utf8",
      ),
    );
  } catch {
    return { chromeIntegration: true };
  }
}

function publishMaintenance(changes = {}) {
  maintenanceState = {
    ...maintenanceState,
    ...changes,
    currentVersion: app.getVersion(),
  };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("maintenance:state", maintenanceState);
  }
  return maintenanceState;
}

function configureUpdaterEvents() {
  autoUpdater.on("checking-for-update", () =>
    publishMaintenance({
      status: "checking",
      message: "Checking the GitHub release channel…",
      progress: 0,
    }),
  );
  autoUpdater.on("update-available", (info) =>
    publishMaintenance({
      status: "available",
      message: `Version ${info.version} is available.`,
      updateAvailable: true,
      latestVersion: info.version || "",
      downloaded: false,
    }),
  );
  autoUpdater.on("update-not-available", (info) =>
    publishMaintenance({
      status: "current",
      message: "Lead Extractor is up to date.",
      updateAvailable: false,
      latestVersion: info?.version || app.getVersion(),
      downloaded: false,
      progress: 0,
    }),
  );
  autoUpdater.on("download-progress", (progress) =>
    publishMaintenance({
      status: "downloading",
      message: `Downloading update · ${Math.round(progress.percent || 0)}%`,
      progress: Math.round(progress.percent || 0),
    }),
  );
  autoUpdater.on("update-downloaded", (info) =>
    publishMaintenance({
      status: "downloaded",
      message: `Version ${info.version} is ready to install.`,
      updateAvailable: true,
      latestVersion: info.version || "",
      downloaded: true,
      progress: 100,
    }),
  );
  autoUpdater.on("error", (error) =>
    publishMaintenance({
      status: "error",
      message: `Update check failed: ${String(error?.message || error).slice(0, 300)}`,
      progress: 0,
    }),
  );
}

function validBounds(value) {
  return (
    value &&
    ["x", "y", "width", "height"].every((key) => Number.isFinite(value[key])) &&
    value.width >= 900 &&
    value.height >= 620
  );
}

function readWindowState() {
  try {
    const state = JSON.parse(fs.readFileSync(windowStatePath(), "utf8"));
    if (validBounds(state.bounds)) {
      const area = screen.getDisplayMatching(state.bounds).workArea;
      const width = Math.min(state.bounds.width, area.width);
      const height = Math.min(state.bounds.height, area.height);
      return {
        ...state,
        bounds: {
          width,
          height,
          x: Math.min(
            Math.max(state.bounds.x, area.x),
            area.x + area.width - width,
          ),
          y: Math.min(
            Math.max(state.bounds.y, area.y),
            area.y + area.height - height,
          ),
        },
      };
    }
  } catch {}
  const area = screen.getPrimaryDisplay().workArea;
  const width = Math.min(1480, area.width);
  const height = Math.min(940, area.height);
  return {
    bounds: {
      width,
      height,
      x: area.x + Math.max(0, Math.round((area.width - width) / 2)),
      y: area.y + Math.max(0, Math.round((area.height - height) / 2)),
    },
    maximized: false,
  };
}

function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const state = {
    bounds: mainWindow.isMaximized()
      ? mainWindow.getNormalBounds()
      : mainWindow.getBounds(),
    maximized: mainWindow.isMaximized(),
  };
  const target = windowStatePath();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, JSON.stringify(state, null, 2));
}

function scheduleStateSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveWindowState, 250);
}

function startupMarkup(title, detail, progress) {
  const clean = (value) => String(value || "").replace(/[&<>"']/g, "");
  const percent = Math.max(2, Math.min(100, Number(progress) || 2));
  return `<!doctype html><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{margin:0;background:#17131e;color:#f6f3fb;font:14px "Segoe UI",sans-serif;display:grid;place-items:center;height:100vh;-webkit-app-region:drag}
    main{width:440px;padding:34px;border:1px solid rgba(255,255,255,.12);border-radius:20px;background:linear-gradient(145deg,#242034,#4931b5);box-shadow:0 30px 80px rgba(0,0,0,.38)}
    .mark{width:44px;height:44px;display:grid;place-items:center;border-radius:13px;background:#f1eeff;color:#4931b5;font-size:22px;font-weight:800}h1{margin:22px 0 8px;font-size:25px;letter-spacing:-.03em}p{margin:0;color:#dcd6e8;line-height:1.55}.track{height:7px;margin-top:25px;overflow:hidden;border-radius:99px;background:rgba(255,255,255,.14)}.bar{height:100%;width:${percent}%;border-radius:inherit;background:#c9baff;transition:width .3s}.note{margin-top:12px;font-size:12px;color:#bfb6cf}
  </style><main><div class="mark">↗</div><h1>${clean(title)}</h1><p>${clean(detail)}</p><div class="track"><div class="bar"></div></div><div class="note">First-time setup can take several minutes. Please keep this window open.</div></main>`;
}

function showStartup(
  title = "Starting Lead Extractor",
  detail = "Preparing your private local workspace…",
  progress = 5,
) {
  if (!app.isPackaged) return;
  if (!startupWindow || startupWindow.isDestroyed()) {
    startupWindow = new BrowserWindow({
      width: 520,
      height: 390,
      frame: false,
      resizable: false,
      show: false,
      backgroundColor: "#17131e",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    startupWindow.once("ready-to-show", () => startupWindow?.show());
  }
  startupWindow.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(startupMarkup(title, detail, progress))}`,
  );
}

function closeStartup() {
  if (startupWindow && !startupWindow.isDestroyed()) startupWindow.close();
  startupWindow = null;
}

async function dashboardReady() {
  try {
    const response = await fetch(`${DASHBOARD_URL}api/health`, {
      signal: AbortSignal.timeout(1000),
    });
    const body = await response.json();
    return response.ok && body.version === "2.0";
  } catch {
    return false;
  }
}

function runProcess(command, args, timeoutMs, options = {}) {
  return new Promise((resolve, reject) => {
    let stderr = "";
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "ignore", "pipe"],
      env: options.env || process.env,
    });
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`${path.basename(command)} timed out`));
    }, timeoutMs);
    child.stderr.on("data", (chunk) => {
      stderr = (stderr + chunk.toString()).slice(-1200);
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve();
      else
        reject(
          new Error(
            stderr.trim() ||
              `${path.basename(command)} exited with code ${code}`,
          ),
        );
    });
  });
}

async function ensurePythonRuntime() {
  const developmentPython = path.join(ROOT, ".venv", "Scripts", "python.exe");
  if (!app.isPackaged && fs.existsSync(developmentPython))
    return developmentPython;
  const target = runtimePython();
  if (fs.existsSync(target)) {
    showStartup(
      "Loading your workspace",
      "The private local runtime is ready. Starting saved services…",
      72,
    );
    return target;
  }
  showStartup(
    "Preparing the local runtime",
    "Checking for a compatible Python installation…",
    12,
  );
  const candidates = process.env.PYTHON
    ? [{ command: process.env.PYTHON, prefix: [] }]
    : [
        { command: "py.exe", prefix: ["-3"] },
        { command: "python.exe", prefix: [] },
      ];
  let selected = null;
  for (const candidate of candidates) {
    try {
      await runProcess(
        candidate.command,
        [...candidate.prefix, "--version"],
        10000,
      );
      selected = candidate;
      break;
    } catch {}
  }
  if (!selected)
    throw new Error(
      "Python 3.10 or newer is required. Install Python, enable ‘Add Python to PATH’, then reopen Lead Extractor.",
    );
  const runtime = path.join(app.getPath("userData"), "runtime");
  fs.mkdirSync(runtime, { recursive: true });
  showStartup(
    "Creating your private runtime",
    "This happens once after installation and keeps app data local.",
    25,
  );
  await runProcess(
    selected.command,
    [...selected.prefix, "-m", "venv", path.join(runtime, ".venv")],
    120000,
  );
  showStartup(
    "Installing research components",
    "Setting up browser, extraction, phone and secure-storage support…",
    42,
  );
  await runProcess(
    target,
    [
      "-m",
      "pip",
      "install",
      "--disable-pip-version-check",
      "-r",
      path.join(ROOT, "requirements.txt"),
    ],
    600000,
  );
  showStartup(
    "Local runtime ready",
    "Starting the lead intelligence workspace…",
    82,
  );
  return target;
}

async function ensureBackend() {
  if (await dashboardReady()) {
    showStartup("Opening Lead Extractor", "The local workspace is ready.", 96);
    return;
  }
  const python = await ensurePythonRuntime();
  const preferences = installerPreferences();
  backend = spawn(
    python,
    ["dashboard.py", "--port", String(DASHBOARD_PORT), "--no-browser"],
    {
      cwd: ROOT,
      windowsHide: true,
      stdio: "ignore",
      env: {
        ...process.env,
        LEAD_EXTRACTOR_HOME: dataRoot(),
        LEAD_EXTRACTOR_CHROME_INTEGRATION:
          preferences.chromeIntegration === false ? "0" : "1",
      },
    },
  );
  showStartup(
    "Starting the research engine",
    "Loading saved searches, AI memory and connected workflows…",
    90,
  );
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (await dashboardReady()) {
      showStartup("Workspace ready", "Opening your dashboard…", 100);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(
    "The local dashboard did not become ready within 15 seconds.",
  );
}

function updateNavigationState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const history = mainWindow.webContents.navigationHistory;
  mainWindow.webContents.send("window:navigation", {
    canGoBack: history.canGoBack(),
    canGoForward: history.canGoForward(),
    maximized: mainWindow.isMaximized(),
  });
}

function createWindow() {
  const state = readWindowState();
  mainWindow = new BrowserWindow({
    ...state.bounds,
    minWidth: 900,
    minHeight: 620,
    frame: false,
    resizable: true,
    maximizable: true,
    minimizable: true,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#f6f3fb",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  if (state.maximized) mainWindow.maximize();
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(DASHBOARD_URL))
      return {
        action: "allow",
        overrideBrowserWindowOptions: {
          parent: mainWindow,
          width: 680,
          height: 820,
          minWidth: 520,
          minHeight: 620,
          autoHideMenuBar: true,
          webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
          },
        },
      };
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith(DASHBOARD_URL)) return;
    event.preventDefault();
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
  });
  for (const event of ["did-navigate", "did-navigate-in-page"])
    mainWindow.webContents.on(event, updateNavigationState);
  mainWindow.on("maximize", updateNavigationState);
  mainWindow.on("unmaximize", updateNavigationState);
  mainWindow.on("resize", scheduleStateSave);
  mainWindow.on("move", scheduleStateSave);
  mainWindow.on("close", saveWindowState);
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    closeStartup();
    updateNavigationState();
  });
  mainWindow.loadURL(`${DASHBOARD_URL}?desktop=1`);
}

ipcMain.handle("window:action", (_event, action) => {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  const history = mainWindow.webContents.navigationHistory;
  if (action === "back" && history.canGoBack()) history.goBack();
  else if (action === "forward" && history.canGoForward()) history.goForward();
  else if (action === "reload") mainWindow.webContents.reload();
  else if (action === "minimize") mainWindow.minimize();
  else if (action === "maximize")
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  else if (action === "close") mainWindow.close();
  updateNavigationState();
  return true;
});

ipcMain.handle("maintenance:status", () => maintenanceState);
ipcMain.handle("maintenance:check", async () => {
  if (!app.isPackaged)
    return publishMaintenance({
      status: "development",
      message: "Update checks run in the installed desktop build.",
    });
  await autoUpdater.checkForUpdates();
  return maintenanceState;
});
ipcMain.handle("maintenance:download", async () => {
  if (!app.isPackaged)
    throw new Error("Update downloads run in the installed desktop build.");
  if (!maintenanceState.updateAvailable)
    throw new Error("Check for an available update first.");
  publishMaintenance({
    status: "downloading",
    message: "Downloading the release package…",
    progress: 0,
  });
  await autoUpdater.downloadUpdate();
  return maintenanceState;
});
ipcMain.handle("maintenance:install", () => {
  if (!maintenanceState.downloaded)
    throw new Error("Download the update before installing it.");
  autoUpdater.quitAndInstall(false, true);
  return true;
});
ipcMain.handle("maintenance:repair", async () => {
  if (!app.isPackaged)
    return publishMaintenance({
      status: "development",
      message: "Runtime repair is available in the installed desktop build.",
    });
  const userData = path.resolve(app.getPath("userData"));
  const runtime = path.resolve(path.join(userData, "runtime"));
  const relative = path.relative(userData, runtime);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative))
    throw new Error("Repair target is outside the application data folder.");
  const backup = `${runtime}.repair-backup-${Date.now()}`;
  publishMaintenance({
    status: "repairing",
    message:
      "Rebuilding the local Python runtime. Saved leads and settings are untouched.",
    progress: 5,
  });
  if (backend && !backend.killed) backend.kill();
  backend = null;
  try {
    if (fs.existsSync(runtime)) fs.renameSync(runtime, backup);
    await ensurePythonRuntime();
    publishMaintenance({
      status: "repairing",
      message: "Runtime rebuilt. Restarting the local service…",
      progress: 85,
    });
    await ensureBackend();
    if (fs.existsSync(backup))
      fs.rmSync(backup, { recursive: true, force: true });
    return publishMaintenance({
      status: "repaired",
      message: "Repair complete. Saved leads and settings were preserved.",
      progress: 100,
    });
  } catch (error) {
    try {
      if (fs.existsSync(runtime))
        fs.rmSync(runtime, { recursive: true, force: true });
      if (fs.existsSync(backup)) fs.renameSync(backup, runtime);
      await ensureBackend();
    } catch {}
    publishMaintenance({
      status: "error",
      message: `Repair failed; the previous runtime was restored. ${String(error?.message || error).slice(0, 260)}`,
      progress: 0,
    });
    throw error;
  }
});
ipcMain.handle("data:backup", async (_event, options = {}) => {
  const stamp = new Date().toISOString().slice(0, 10);
  const chosen = await dialog.showSaveDialog(mainWindow, {
    title: "Save Lead Extractor backup",
    defaultPath: path.join(
      app.getPath("documents"),
      `Lead-Extractor-Backup-${stamp}.leadbackup`,
    ),
    filters: [{ name: "Lead Extractor backup", extensions: ["leadbackup"] }],
  });
  if (chosen.canceled || !chosen.filePath) return { canceled: true };
  const args = [
    path.join(ROOT, "backup_manager.py"),
    "create",
    "--root",
    dataRoot(),
    "--file",
    chosen.filePath,
  ];
  if (options.personal === true) args.push("--personal");
  await runProcess(backupPython(), args, 180000);
  return {
    canceled: false,
    path: chosen.filePath,
    name: path.basename(chosen.filePath),
    personal: options.personal === true,
  };
});
ipcMain.handle("data:restore", async () => {
  const chosen = await dialog.showOpenDialog(mainWindow, {
    title: "Restore Lead Extractor backup",
    properties: ["openFile"],
    filters: [{ name: "Lead Extractor backup", extensions: ["leadbackup"] }],
  });
  if (chosen.canceled || !chosen.filePaths[0]) return { canceled: true };
  const source = chosen.filePaths[0];
  await runProcess(
    backupPython(),
    [
      path.join(ROOT, "backup_manager.py"),
      "inspect",
      "--root",
      dataRoot(),
      "--file",
      source,
    ],
    30000,
  );
  if (backend && !backend.killed) backend.kill();
  backend = null;
  await new Promise((resolve) => setTimeout(resolve, 500));
  try {
    await runProcess(
      backupPython(),
      [
        path.join(ROOT, "backup_manager.py"),
        "restore",
        "--root",
        dataRoot(),
        "--file",
        source,
      ],
      180000,
    );
    await ensureBackend();
    mainWindow.webContents.reload();
    return { canceled: false, name: path.basename(source), restored: true };
  } catch (error) {
    await ensureBackend().catch(() => {});
    throw error;
  }
});
ipcMain.handle("ai:benchmark", async () => {
  await runProcess(
    backupPython(),
    [path.join(ROOT, "ai_benchmark.py")],
    900000,
    { env: { ...process.env, LEAD_EXTRACTOR_HOME: dataRoot() } },
  );
  return { complete: true };
});

const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) app.quit();
app.on("second-instance", () => {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.focus();
});

app.whenReady().then(async () => {
  if (!singleInstance) return;
  app.setAppUserModelId("local.leadextractor.desktop");
  configureUpdaterEvents();
  showStartup();
  try {
    await ensureBackend();
    createWindow();
  } catch (error) {
    closeStartup();
    const failure = new BrowserWindow({
      width: 640,
      height: 320,
      autoHideMenuBar: true,
    });
    const message = String(error?.message || error).replace(/[&<>"']/g, "");
    failure.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(`<style>body{font:16px Segoe UI;padding:32px;color:#10202c}h1{font-size:24px}</style><h1>Lead Extractor could not start</h1><p>${message}</p><p>The browser dashboard and saved data were not changed.</p>`)}`,
    );
  }
  if (app.isPackaged) {
    setTimeout(() => autoUpdater.checkForUpdates().catch(() => {}), 8000);
    setInterval(
      () => autoUpdater.checkForUpdates().catch(() => {}),
      6 * 60 * 60 * 1000,
    );
  }
});

app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => {
  clearTimeout(saveTimer);
  saveWindowState();
  if (backend && !backend.killed) backend.kill();
});
