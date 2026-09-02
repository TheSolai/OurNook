import { useEffect, useRef, useState } from "react";
import { useCompanionStore, useUIStore } from "./stores";

const API = "/api";

type Tab = "import" | "export";

interface PreviewCard {
  name: string;
  description: string;
  personality: string;
  first_mes: string;
  tags: string[];
  extensions: { nook: Record<string, unknown> };
}

export function CardIOPanel() {
  const { t: _t } = useTranslationShim();
  const showToast = useUIStore((s) => s.showToast);
  const { roster, fetchRoster, setActive } = useCompanionStore();
  const openEditor = useUIStore((s) => s.openEditor);
  const [tab, setTab] = useState<Tab>("import");
  const [importing, setImporting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Import tab state
  const [pasteText, setPasteText] = useState("");
  const [lastImported, setLastImported] = useState<{ name: string; id: string; fromFile?: string } | null>(null);

  // Export tab state
  const [exportFormat, setExportFormat] = useState<"json" | "png">("json");
  // Expose the current export format to the global ⌘⇧E shortcut
  useEffect(() => {
    window.__cardioExportFormat = exportFormat;
  }, [exportFormat]);
  const [previewFor, setPreviewFor] = useState<string | null>(null);
  const [previewCard, setPreviewCard] = useState<PreviewCard | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    void fetchRoster();
  }, [fetchRoster]);

  async function importFile(file: File) {
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) {
      showToast("File too large (50MB max)", "err");
      return;
    }
    setImporting(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`${API}/companions/import-file`, { method: "POST", body: form });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Import failed");
      setLastImported({ name: data.name, id: data.companion.id, fromFile: file.name });
      showToast(`✓ Imported ${data.name}`, "ok");
      void fetchRoster();
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setImporting(false);
    }
  }

  async function importPasted() {
    if (!pasteText.trim()) return;
    setImporting(true);
    try {
      const r = await fetch(`${API}/companions/import-paste`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ json: pasteText }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Import failed");
      setLastImported({ name: data.name, id: data.companion.id });
      setPasteText("");
      showToast(`✓ Imported ${data.name}`, "ok");
      void fetchRoster();
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setImporting(false);
    }
  }

  function exportCompanion(id: string, name: string) {
    const url = `${API}/companions/${id}/export?format=${exportFormat}`;
    // Use a hidden link with the Authorization-style download attribute.
    // pywebview will prompt to save the file.
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sanitize(name)}.${exportFormat}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast(`Exporting ${name} as ${exportFormat.toUpperCase()}…`, "ok");
  }

  async function openPreview(id: string) {
    setPreviewFor(id);
    setPreviewCard(null);
    setPreviewLoading(true);
    try {
      const r = await fetch(`${API}/companions/${id}/card-preview`);
      if (!r.ok) throw new Error("Could not load card");
      setPreviewCard(await r.json());
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
      setPreviewFor(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) void importFile(f);
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Cards</h2>
        <p>
          Bring companions in and out of OurNook. Compatible with{" "}
          <a href="https://docs.sillytavern.app/usage/core-concepts/charactercard/" target="_blank" rel="noreferrer">
            SillyTavern character cards
          </a>{" "}
          — the standard for the 12K+ community.
        </p>
      </div>

      <div className="subtabs">
        <button className={`subtab ${tab === "import" ? "active" : ""}`} onClick={() => setTab("import")}>
          ⬇ Import
        </button>
        <button className={`subtab ${tab === "export" ? "active" : ""}`} onClick={() => setTab("export")}>
          ⬆ Export
        </button>
      </div>

      {/* ── IMPORT TAB ── */}
      {tab === "import" && (
        <div className="col-lg">
          {/* Drop zone */}
          <div
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="dropzone-icon">⬇</div>
            <div className="dropzone-title">
              {importing ? "Importing…" : "Drop a card file here, or click to browse"}
            </div>
            <div className="dropzone-hint">
              Accepts <code>.json</code> and <code>.png</code> (PNG cards with embedded character data). Max 50MB.
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,.png,application/json,image/png"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importFile(f);
                e.target.value = "";
              }}
            />
          </div>

          {lastImported && (
            <div className="card success">
              <div className="card-header">
                <div>
                  <div className="card-title">✓ Imported {lastImported.name}</div>
                  <div className="card-subtitle">
                    {lastImported.fromFile ? `from ${lastImported.fromFile}` : "from pasted JSON"}
                  </div>
                </div>
                <div className="row">
                  <button
                    onClick={() => {
                      setActive(lastImported.id);
                      useUIStore.getState().setTab("chat");
                    }}
                  >
                    Open in chat
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Paste JSON */}
          <div className="settings-section">
            <div className="settings-section-title">Paste card JSON</div>
            <p className="caption" style={{ marginBottom: 8 }}>
              For when you have card JSON from a website, generator, or another tool.
            </p>
            <textarea
              placeholder='{ "name": "Your character", "description": "...", "personality": "...", ... }'
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              rows={8}
              style={{ fontFamily: "SF Mono, Menlo, monospace", fontSize: 12 }}
            />
            <div className="row" style={{ marginTop: 8 }}>
              <button
                className="primary"
                onClick={importPasted}
                disabled={importing || !pasteText.trim()}
              >
                {importing ? "Importing…" : "Import from JSON"}
              </button>
              {pasteText && (
                <button onClick={() => setPasteText("")} className="ghost">Clear</button>
              )}
            </div>
          </div>

          <div className="models-info">
            <strong>Where to find cards:</strong>{" "}
            <a href="https://chub.ai" target="_blank" rel="noreferrer">chub.ai</a>,{" "}
            <a href="https://aicharactercards.com" target="_blank" rel="noreferrer">aicharactercards.com</a>,{" "}
            <a href="https://www.characterhub.org" target="_blank" rel="noreferrer">characterhub.org</a>,{" "}
            <a href="https://www.janitorai.com" target="_blank" rel="noreferrer">janitorai.com</a>.{" "}
            Most export as <code>.json</code> or <code>.png</code> — drop one in and it just works.
          </div>
        </div>
      )}

      {/* ── EXPORT TAB ── */}
      {tab === "export" && (
        <div className="col-lg">
          <div className="settings-section">
            <div className="settings-section-title">Format</div>
            <div className="row" style={{ gap: 8 }}>
              <button
                className={exportFormat === "json" ? "primary" : ""}
                onClick={() => setExportFormat("json")}
              >
                📄 JSON
              </button>
              <button
                className={exportFormat === "png" ? "primary" : ""}
                onClick={() => setExportFormat("png")}
              >
                🖼️ PNG card
              </button>
            </div>
            <p className="caption" style={{ marginTop: 8 }}>
              {exportFormat === "json"
                ? "Plain JSON — easy to read, edit, and share. Compatible with SillyTavern, Agnostic, RisuAI, and most other tools."
                : "PNG with the card embedded in a tEXt chunk. Looks like a regular image; opening with a card reader shows the character. Works in SillyTavern, chub.ai, and any tool that reads V2/V3 cards."}
            </p>
          </div>

          <div className="settings-section">
            <div className="settings-section-title">Your companions</div>
            {roster.length === 0 ? (
              <p className="caption">No companions to export. Create one first.</p>
            ) : (
              <div className="col-sm">
                {roster.map((c) => (
                  <div key={c.id} className="settings-row" style={{ padding: "12px 14px", background: "var(--bg-elev)", borderRadius: "var(--radius)", border: "1px solid var(--border-2)" }}>
                    <div className="row" style={{ gap: 12, flex: 1, minWidth: 0 }}>
                      <div
                        className="chat-avatar-initials"
                        style={{
                          width: 36, height: 36, fontSize: 14,
                          background: `linear-gradient(135deg, hsl(${(c.name.charCodeAt(0) * 137) % 360}, 55%, 50%), hsl(${((c.name.charCodeAt(0) * 137) + 40) % 360}, 45%, 38%))`,
                        }}
                      >
                        {c.name.slice(0, 1).toUpperCase()}
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="settings-row-label">{c.name}</div>
                        <div className="settings-row-hint">
                          <span className="tag accent" style={{ marginRight: 6 }}>{c.relationship_type}</span>
                          <span className="tag muted" style={{ marginRight: 6 }}>{c.memory_mode}</span>
                          {c.model_name && <span className="tag muted">{c.model_name}</span>}
                        </div>
                      </div>
                    </div>
                    <div className="row" style={{ gap: 6 }}>
                      <button className="ghost" onClick={() => openPreview(c.id)}>Preview</button>
                      <button className="ghost" onClick={() => openEditor(c.id)}>✎ Edit</button>
                      <button className="primary" onClick={() => exportCompanion(c.id, c.name)}>
                        ⬇ Export
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── PREVIEW MODAL ── */}
      {previewFor && (
        <div className="modal-backdrop" onClick={() => setPreviewFor(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Card preview · {roster.find((c) => c.id === previewFor)?.name}</h2>
              <button className="close-btn" onClick={() => setPreviewFor(null)}>×</button>
            </div>
            <div className="modal-body">
              {previewLoading ? (
                <p className="caption">Loading…</p>
              ) : previewCard ? (
                <div className="col">
                  <div>
                    <div className="micro">Name</div>
                    <div className="body-lg" style={{ marginTop: 4 }}>{previewCard.name || "—"}</div>
                  </div>
                  <div>
                    <div className="micro">Description</div>
                    <pre className="soul-preview" style={{ minHeight: 60, maxHeight: 160, fontFamily: "inherit" }}>
                      {previewCard.description || "—"}
                    </pre>
                  </div>
                  <div>
                    <div className="micro">Personality</div>
                    <pre className="soul-preview" style={{ minHeight: 60, maxHeight: 120, fontFamily: "inherit" }}>
                      {previewCard.personality || "—"}
                    </pre>
                  </div>
                  {previewCard.first_mes && (
                    <div>
                      <div className="micro">First message</div>
                      <pre className="soul-preview" style={{ minHeight: 60, maxHeight: 120, fontFamily: "inherit" }}>
                        {previewCard.first_mes}
                      </pre>
                    </div>
                  )}
                  {previewCard.tags?.length > 0 && (
                    <div>
                      <div className="micro">Tags</div>
                      <div className="row" style={{ flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                        {previewCard.tags.map((t, i) => <span key={i} className="tag muted">{t}</span>)}
                      </div>
                    </div>
                  )}
                  {previewCard.extensions?.nook && Object.keys(previewCard.extensions.nook).length > 0 && (
                    <div>
                      <div className="micro">OurNook extensions</div>
                      <pre className="soul-preview" style={{ fontSize: 11, fontFamily: "SF Mono, Menlo, monospace" }}>
                        {JSON.stringify(previewCard.extensions.nook, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ) : (
                <p className="caption">No data.</p>
              )}
            </div>
            <div className="modal-footer">
              <span className="spacer" />
              <button
                className="primary"
                onClick={() => {
                  const c = roster.find((x) => x.id === previewFor);
                  if (c) exportCompanion(c.id, c.name);
                }}
              >
                ⬇ Export as {exportFormat.toUpperCase()}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function sanitize(name: string): string {
  return name.replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "companion";
}

// Stub for t (i18n not strictly needed in this panel right now)
function useTranslationShim() {
  return { t: (s: string) => s };
}
