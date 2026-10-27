const { app, BrowserWindow, ipcMain, shell, screen } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

app.setName("Lead Extractor");

const ROOT = app.isPackaged
  ? path.join(process.resourcesPath, "backend")
  : path.resolve(__dirname, "..");
const DASHBOARD_URL = "http://127.0.0.1:8788/";
let mainWindow = null;
let backend = null;
let saveTimer = null;

function dataRoot() { return app.isPackaged ? app.getPath("userData") : ROOT; }
function windowStatePath() { return path.join(dataRoot(), "data", "electron-window.json"); }
function runtimePython() { return path.join(app.getPath("userData"), "runtime", ".venv", "Scripts", "python.exe"); }
function installerPreferences() {
  try { return JSON.parse(fs.readFileSync(path.join(app.getPath("userData"), "installer-preferences.json"), "utf8")); }
  catch { return { chromeIntegration: true }; }
}

function validBounds(value) {
  return value && ["x", "y", "width", "height"].every((key) => Number.isFinite(value[key])) && value.width >= 900 && value.height >= 620;
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
          x: Math.min(Math.max(state.bounds.x, area.x), area.x + area.width - width),
          y: Math.min(Math.max(state.bounds.y, area.y), area.y + area.height - height),
        },
      };
    }
  } catch {}
  const area = screen.getPrimaryDisplay().workArea;
  const width = Math.min(1480, area.width);
  const height = Math.min(940, area.height);
  return { bounds: { width, height, x: area.x + Math.max(0, Math.round((area.width - width) / 2)), y: area.y + Math.max(0, Math.round((area.height - height) / 2)) }, maximized: false };
}

function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const state = { bounds: mainWindow.isMaximized() ? mainWindow.getNormalBounds() : mainWindow.getBounds(), maximized: mainWindow.isMaximized() };
  const target = windowStatePath();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, JSON.stringify(state, null, 2));
}

function scheduleStateSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveWindowState, 250);
}

async function dashboardReady() {
  try {
    const response = await fetch(`${DASHBOARD_URL}api/health`, { signal: AbortSignal.timeout(1000) });
    const body = await response.json();
    return response.ok && body.version === "2.0";
  } catch { return false; }
}

function runProcess(command, args, timeoutMs) {
  return new Promise((resolve, reject) => {
    let stderr = "";
    const child = spawn(command, args, { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] });
    const timer = setTimeout(() => { child.kill(); reject(new Error(`${path.basename(command)} timed out`)); }, timeoutMs);
    child.stderr.on("data", (chunk) => { stderr = (stderr + chunk.toString()).slice(-1200); });
    child.on("error", (error) => { clearTimeout(timer); reject(error); });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve();
      else reject(new Error(stderr.trim() || `${path.basename(command)} exited with code ${code}`));
    });
  });
}

async function ensurePythonRuntime() {
  const developmentPython = path.join(ROOT, ".venv", "Scripts", "python.exe");
  if (!app.isPackaged && fs.existsSync(developmentPython)) return developmentPython;
  const target = runtimePython();
  if (fs.existsSync(target)) return target;
  const candidates = process.env.PYTHON
    ? [{ command: process.env.PYTHON, prefix: [] }]
    : [{ command: "py.exe", prefix: ["-3"] }, { command: "python.exe", prefix: [] }];
  let selected = null;
  for (const candidate of candidates) {
    try { await runProcess(candidate.command, [...candidate.prefix, "--version"], 10000); selected = candidate; break; }
    catch {}
  }
  if (!selected) throw new Error("Python 3.10 or newer is required. Install Python, enable ‘Add Python to PATH’, then reopen Lead Extractor.");
  const runtime = path.join(app.getPath("userData"), "runtime");
  fs.mkdirSync(runtime, { recursive: true });
  await runProcess(selected.command, [...selected.prefix, "-m", "venv", path.join(runtime, ".venv")], 120000);
  await runProcess(target, ["-m", "pip", "install", "--disable-pip-version-check", "-r", path.join(ROOT, "requirements.txt")], 600000);
  return target;
}

async function ensureBackend() {
  if (await dashboardReady()) return;
  const python = await ensurePythonRuntime();
  const preferences = installerPreferences();
  backend = spawn(python, ["dashboard.py", "--port", "8788", "--no-browser"], {
    cwd: ROOT,
    windowsHide: true,
    stdio: "ignore",
    env: {
      ...process.env,
      LEAD_EXTRACTOR_HOME: dataRoot(),
      LEAD_EXTRACTOR_CHROME_INTEGRATION: preferences.chromeIntegration === false ? "0" : "1",
    },
  });
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (await dashboardReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("The local dashboard did not become ready within 15 seconds.");
}

function updateNavigationState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const history = mainWindow.webContents.navigationHistory;
  mainWindow.webContents.send("window:navigation", { canGoBack: history.canGoBack(), canGoForward: history.canGoForward(), maximized: mainWindow.isMaximized() });
}

function createWindow() {
  const state = readWindowState();
  mainWindow = new BrowserWindow({
    ...state.bounds, minWidth: 900, minHeight: 620, frame: false, resizable: true,
    maximizable: true, minimizable: true, show: false, autoHideMenuBar: true,
    backgroundColor: "#f6f3fb",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  if (state.maximized) mainWindow.maximize();
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(DASHBOARD_URL)) return { action: "allow", overrideBrowserWindowOptions: { parent: mainWindow, width: 680, height: 820, minWidth: 520, minHeight: 620, autoHideMenuBar: true, webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } } };
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith(DASHBOARD_URL)) return;
    event.preventDefault();
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
  });
  for (const event of ["did-navigate", "did-navigate-in-page"]) mainWindow.webContents.on(event, updateNavigationState);
  mainWindow.on("maximize", updateNavigationState);
  mainWindow.on("unmaximize", updateNavigationState);
  mainWindow.on("resize", scheduleStateSave);
  mainWindow.on("move", scheduleStateSave);
  mainWindow.on("close", saveWindowState);
  mainWindow.once("ready-to-show", () => { mainWindow.show(); updateNavigationState(); });
  mainWindow.loadURL(`${DASHBOARD_URL}?desktop=1`);
}

ipcMain.handle("window:action", (_event, action) => {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  const history = mainWindow.webContents.navigationHistory;
  if (action === "back" && history.canGoBack()) history.goBack();
  else if (action === "forward" && history.canGoForward()) history.goForward();
  else if (action === "reload") mainWindow.webContents.reload();
  else if (action === "minimize") mainWindow.minimize();
  else if (action === "maximize") mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  else if (action === "close") mainWindow.close();
  updateNavigationState();
  return true;
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
  try { await ensureBackend(); createWindow(); }
  catch (error) {
    const failure = new BrowserWindow({ width: 640, height: 320, autoHideMenuBar: true });
    const message = String(error?.message || error).replace(/[&<>"']/g, "");
    failure.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`<style>body{font:16px Segoe UI;padding:32px;color:#10202c}h1{font-size:24px}</style><h1>Lead Extractor could not start</h1><p>${message}</p><p>The browser dashboard and saved data were not changed.</p>`)}`);
  }
});

app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => { clearTimeout(saveTimer); saveWindowState(); if (backend && !backend.killed) backend.kill(); });

