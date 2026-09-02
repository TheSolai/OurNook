import { useEffect } from "react";

declare global {
  interface Window {
    __cardioExportFormat?: "json" | "png";
    __cardioWantImport?: boolean;
  }
}
import { useTranslation } from "react-i18next";
import {
  useCompanionStore,
  useStatusStore,
  useUIStore,
} from "./stores";
import { Sidebar } from "./Sidebar";
import { ChatPanel } from "./ChatPanel";
import { MemoryPanel } from "./MemoryPanel";
import { ArtPanel } from "./ArtPanel";
import { SettingsPanel } from "./SettingsPanel";
import { ModelsPanel } from "./ModelsPanel";
import { CardIOPanel } from "./CardIOPanel";
import { CompanionWizard } from "./CompanionWizard";
import { BackupPanel } from "./BackupPanel";
import { EditCompanionPanel } from "./EditCompanionPanel";
import { InnerLifePanel } from "./InnerLifePanel";

function StatusBar() {
  const { ollama, appInfo } = useStatusStore();

  return (
    <div className="status-bar">
      <div className="status-bar-status">
        {ollama?.healthy ? (
          <>
            <span className="dot ok" />
            <span>Ollama connected</span>
            <span className="dim" style={{ fontFamily: "SF Mono, Menlo, monospace" }}>· {ollama.url}</span>
          </>
        ) : ollama === null ? (
          <>
            <span className="dot warn" />
            <span>Checking Ollama…</span>
          </>
        ) : (
          <>
            <span className="dot err" />
            <span>Ollama unreachable</span>
            <span className="dim">· {ollama.error ?? ollama.url}</span>
          </>
        )}
        {ollama && !ollama.image_gen_platform_supported && ollama.image_gen_platform_reason && (
          <span
            className="tag"
            style={{ marginLeft: 8 }}
            title={`Ollama native image gen: ${ollama.image_gen_platform_reason}\nOurNook falls back to LLM-generated SVG art — always works.`}
          >
            ✦ AI art (vector)
          </span>
        )}
      </div>
      <div className="status-bar-version">
        <span className="dim">OurNook</span>
        <span className="dim">v{appInfo?.version ?? "…"}</span>
        <span className="dim">·</span>
        <span className="dim">{appInfo?.platform ?? ""}</span>
      </div>
    </div>
  );
}

function Tabs() {
  const { t } = useTranslation();
  const { activeTab, setTab } = useUIStore();
  const tabs = [
    { id: "chat", label: t("nav.chat") },
    { id: "memory", label: t("nav.memory") },
    { id: "inner", label: t("nav.inner") || "Inner life" },
    { id: "art", label: t("nav.art") },
    { id: "models", label: t("nav.models") },
    { id: "cards", label: t("nav.cards") },
    { id: "settings", label: t("nav.settings") },
  ] as const;
  return (
    <div className="tabs">
      {tabs.map((tt) => (
        <button
          key={tt.id}
          className={`tab ${tt.id === activeTab ? "active" : ""}`}
          onClick={() => setTab(tt.id)}
        >
          {tt.label}
        </button>
      ))}
    </div>
  );
}

function Toast() {
  const toast = useUIStore((s) => s.toast);
  if (!toast) return null;
  return (
    <div className={`toast ${toast.kind}`} key={toast.id}>
      {toast.text}
    </div>
  );
}

export default function App() {
  const { refreshAll } = useStatusStore();
  const { activeTab, showWizard, closeWizard, showBackup, closeBackup, editingId, closeEditor, showToast } = useUIStore();
  const { fetchRoster } = useCompanionStore();

  useEffect(() => {
    void refreshAll();
    void fetchRoster();
  }, [refreshAll, fetchRoster]);

  // Global keyboard shortcuts (Cmd/Ctrl-N, Cmd/Ctrl-E, Cmd/Ctrl-1..6)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      const k = e.key.toLowerCase();
      if (k === "n" && !e.shiftKey) { e.preventDefault(); useUIStore.getState().openWizard(); return; }
      if (k === "e" && !e.shiftKey) {
        e.preventDefault();
        const id = useCompanionStore.getState().activeId;
        if (id) useUIStore.getState().openEditor(id);
        return;
      }
      if (k === "i" && !e.shiftKey) {
        e.preventDefault();
        useUIStore.getState().setTab("cards");
        return;
      }
      if (k === "e" && e.shiftKey) {
        e.preventDefault();
        const id = useCompanionStore.getState().activeId;
        if (id) {
          const c = useCompanionStore.getState().roster.find((x) => x.id === id);
          if (c) {
            const url = `/api/companions/${id}/export?format=${window.__cardioExportFormat || "json"}`;
            const a = document.createElement("a");
            a.href = url;
            a.download = `${c.name.replace(/[^A-Za-z0-9_-]+/g, "_") || "companion"}.${window.__cardioExportFormat || "json"}`;
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
          }
        }
        return;
      }
      if (k === "b" && !e.shiftKey) {
        e.preventDefault();
        useUIStore.getState().openBackup();
        return;
      }
      if (k === "r" && !e.shiftKey) {
        e.preventDefault();
        window.location.reload();
        return;
      }
      if (k >= "1" && k <= "6" && !e.shiftKey) {
        e.preventDefault();
        const tabs = ["chat", "memory", "art", "models", "cards", "settings"] as const;
        useUIStore.getState().setTab(tabs[parseInt(k) - 1]);
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // (v0.15 — the wizard no longer needs server-side quiz constants.
  // It loads Enneagram types + quiz questions on its own.)

  // Heartbeat poll — every 5s. Detects when the FastAPI server is offline
  // and shows a clear banner instead of a hanging spinner.
  const { checkHeartbeat } = useStatusStore();
  useEffect(() => {
    void checkHeartbeat();
    const id = setInterval(() => { void checkHeartbeat(); }, 5000);
    return () => clearInterval(id);
  }, [checkHeartbeat]);

  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        {!useStatusStore.getState().apiOnline && (
          <div className="api-offline-banner">
            <span className="api-offline-icon">⚠</span>
            <span><strong>Server offline</strong> — the OurNook API isn't responding. Restart the app to recover. Recent changes are still saved locally.</span>
          </div>
        )}
        <StatusBar />
        <Tabs />
        {activeTab === "chat" && <ChatPanel />}
        {activeTab === "memory" && <MemoryPanel />}
        {activeTab === "inner" && <InnerLifePanel />}
        {activeTab === "art" && <ArtPanel />}
        {activeTab === "models" && <ModelsPanel />}
        {activeTab === "cards" && <CardIOPanel />}
        {activeTab === "settings" && <SettingsPanel />}
      </div>
      {showWizard && (
        <CompanionWizard
          onClose={closeWizard}
          onCreated={() => {
            closeWizard();
            showToast("✦ Companion created");
          }}
        />
      )}
      {showBackup && (
        <BackupPanel
          onClose={closeBackup}
          showToast={(msg) => showToast(msg, "ok")}
        />
      )}
      {editingId && (
        <EditCompanionPanel
          companionId={editingId}
          onClose={closeEditor}
        />
      )}
      <Toast />
    </div>
  );
}
