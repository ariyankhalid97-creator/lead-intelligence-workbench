const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("leadFinderWindow", {
  action: (name) => ipcRenderer.invoke("window:action", name),
  onNavigation: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on("window:navigation", listener);
    return () => ipcRenderer.removeListener("window:navigation", listener);
  },
});

