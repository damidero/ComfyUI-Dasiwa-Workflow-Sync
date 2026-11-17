import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Pick Spanish or English labels from the ComfyUI locale (fallback: browser language).
function isSpanish() {
  try {
    const loc = localStorage.getItem("Comfy.Settings.Comfy.Locale")
      || app?.ui?.settings?.getSettingValue?.("Comfy.Locale")
      || navigator.language || "";
    return String(loc).toLowerCase().startsWith("es");
  } catch (e) {
    return true;
  }
}
const ES = isSpanish();
const T = ES
  ? {
      enabled: "Sincronizar workflows de DaSiWa",
      enabledTip: "Descarga y actualiza en segundo plano los workflows de DaSiWa en workflows/Dasiwa.",
      mode: "Carpetas a descargar",
      modeTip: "Solo activos: borra las carpetas descatalogadas. Tus versiones modificadas se guardan en Dasiwa/Custom User.",
      active: "Solo activos",
      all: "Todos",
      started: "Sincronizando workflows de DaSiWa...",
    }
  : {
      enabled: "Sync DaSiWa workflows",
      enabledTip: "Downloads and updates the DaSiWa workflows into workflows/Dasiwa in the background.",
      mode: "Folders to download",
      modeTip: "Active only: removes deprecated folders. Your edited versions are kept in Dasiwa/Custom User.",
      active: "Active only",
      all: "All",
      started: "Syncing DaSiWa workflows...",
    };

const ID_ENABLED = "DasiwaSync.Enabled";
const ID_MODE = "DasiwaSync.Mode";

let pushTimer = null;
function pushConfig(runAfter) {
  clearTimeout(pushTimer);
  pushTimer = setTimeout(async () => {
    try {
      const s = app.ui.settings;
      const body = {
        enabled: s.getSettingValue(ID_ENABLED, true),
        mode: s.getSettingValue(ID_MODE, "active"),
      };
      await api.fetchApi("/dasiwa_sync/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (runAfter && body.enabled) {
        await api.fetchApi("/dasiwa_sync/run", { method: "POST" });
        try {
          app.extensionManager?.toast?.add({ severity: "info", summary: "DaSiWa", detail: T.started, life: 3000 });
        } catch (e) {}
      }
    } catch (e) {
      console.warn("[Dasiwa Sync]", e);
    }
  }, 400);
}

// onChange fires once on load with oldValue undefined: only sync the config then.
function onChange(newVal, oldVal) {
  const changed = oldVal !== undefined && oldVal !== null && newVal !== oldVal;
  pushConfig(changed);
}

app.registerExtension({
  name: "DasiwaSync.WorkflowSync",
  settings: [
    {
      id: ID_ENABLED,
      category: ["Dasiwa Sync", "Workflows", "Enabled"],
      name: T.enabled,
      tooltip: T.enabledTip,
      type: "boolean",
      defaultValue: true,
      onChange,
    },
    {
      id: ID_MODE,
      category: ["Dasiwa Sync", "Workflows", "Mode"],
      name: T.mode,
      tooltip: T.modeTip,
      type: "combo",
      options: [
        { text: T.active, value: "active" },
        { text: T.all, value: "all" },
      ],
      defaultValue: "active",
      onChange,
    },
  ],
  async setup() {
    // If the browser setting differs from what the server used at startup, re-sync.
    try {
      const st = await (await api.fetchApi("/dasiwa_sync/status")).json();
      const s = app.ui.settings;
      const en = s.getSettingValue(ID_ENABLED, true);
      const md = s.getSettingValue(ID_MODE, "active");
      const differs = st?.config && (st.config.enabled !== en || st.config.mode !== md);
      pushConfig(Boolean(differs));
    } catch (e) {
      pushConfig(false);
    }
  },
});
