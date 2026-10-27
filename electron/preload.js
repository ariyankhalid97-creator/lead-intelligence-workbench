const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("leadFinderWindow", {
  action: (name) => ipcRenderer.invoke("window:action", name),
  onNavigation: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on("window:navigation", listener);
    return () => ipcRenderer.removeListener("window:navigation", listener);
  },
  maintenanceStatus: () => ipcRenderer.invoke("maintenance:status"),
  checkForUpdates: () => ipcRenderer.invoke("maintenance:check"),
  downloadUpdate: () => ipcRenderer.invoke("maintenance:download"),
  installUpdate: () => ipcRenderer.invoke("maintenance:install"),
  repairRuntime: () => ipcRenderer.invoke("maintenance:repair"),
  onMaintenance: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on("maintenance:state", listener);
    return () => ipcRenderer.removeListener("maintenance:state", listener);
  },
});
