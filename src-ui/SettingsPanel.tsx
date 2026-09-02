import { useTranslation } from "react-i18next";
import { useStatusStore, useUIStore } from "./stores";

const LANGUAGES = [
  { id: "en", label: "English" },
  { id: "es", label: "Español" },
  { id: "fr", label: "Français" },
  { id: "de", label: "Deutsch" },
  { id: "ja", label: "日本語" },
  { id: "ko", label: "한국어" },
  { id: "pt-BR", label: "Português (Brasil)" },
  { id: "zh-CN", label: "中文 (简体)" },
];

export function SettingsPanel() {
  const { i18n } = useTranslation();
  const { appInfo, ollama, ollamaModels, refreshAll } = useStatusStore();
  const { openBackup, setTab } = useUIStore();

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Settings</h2>
        <p>Personalize OurNook — language, model, and your data.</p>
      </div>

      {/* Language */}
      <div className="settings-section">
        <div className="settings-section-title">Language</div>
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Interface language</div>
            <div className="settings-row-hint">UI text and system messages</div>
          </div>
          <select
            value={i18n.language}
            onChange={(e) => void i18n.changeLanguage(e.target.value)}
            style={{ minWidth: 200 }}
          >
            {LANGUAGES.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </div>
      </div>

      {/* Companions / Backup */}
      <div className="settings-section">
        <div className="settings-section-title">Companions</div>
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Backup &amp; restore</div>
            <div className="settings-row-hint">Export companions as ZIP. All soul, messages, memories, diary, art included.</div>
          </div>
          <button onClick={openBackup}>⇪ Open backup</button>
        </div>
      </div>

      {/* Ollama */}
      <div className="settings-section">
        <div className="settings-section-title">Ollama</div>
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Connection</div>
            <div className="settings-row-hint">
              <code>{ollama?.url ?? "—"}</code>
              {ollama?.error && <span className="dim"> · {ollama.error}</span>}
            </div>
          </div>
          <div className="row">
            <span className={`tag ${ollama?.healthy ? "success" : "danger"}`}>
              {ollama?.healthy ? "● connected" : "○ unreachable"}
            </span>
            <button onClick={() => void refreshAll()}>↻ Refresh</button>
          </div>
        </div>

        <div className="settings-row">
          <div>
            <div className="settings-row-label">Installed models</div>
            <div className="settings-row-hint">{ollamaModels.length} model{ollamaModels.length === 1 ? "" : "s"} on disk</div>
          </div>
          <button onClick={() => setTab("models")}>Browse recommended →</button>
        </div>

        {ollama && !ollama.image_gen_platform_supported && ollama.image_gen_platform_reason && (
          <div className="card" style={{ borderColor: "var(--warning)", marginTop: 8 }}>
            <div className="row" style={{ gap: 10 }}>
              <span className="tag warning">⚠ Art</span>
              <div className="body-sm" style={{ color: "var(--text-2)" }}>{ollama.image_gen_platform_reason}</div>
            </div>
          </div>
        )}
      </div>

      {/* About */}
      <div className="settings-section">
        <div className="settings-section-title">About</div>
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-label">Version</div>
            <div className="stat-value">{appInfo?.version ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Platform</div>
            <div className="stat-value">{appInfo?.platform ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Data folder</div>
            <div className="stat-value" style={{ fontSize: 12, fontFamily: "SF Mono, Menlo, monospace", fontWeight: 500, wordBreak: "break-all" }}>
              {appInfo?.data_dir ?? "—"}
            </div>
          </div>
        </div>
        <p className="caption" style={{ marginTop: 16 }}>
          <strong style={{ color: "var(--text)" }}>100% local · 0% telemetry · 0% subscription.</strong> Your companions live on your machine. Your data never leaves it.
        </p>
      </div>
    </div>
  );
}
