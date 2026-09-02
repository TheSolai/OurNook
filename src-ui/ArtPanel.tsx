import { useEffect, useRef, useState } from "react";
import { useArtStore, useCompanionStore, useStatusStore, useUIStore } from "./stores";

const SIZES = [
  { id: "512x512", label: "512 × 512" },
  { id: "768x768", label: "768 × 768" },
  { id: "1024x1024", label: "1024 × 1024" },
  { id: "1024x1536", label: "1024 × 1536 (portrait)" },
  { id: "1536x1024", label: "1536 × 1024 (landscape)" },
];

// Right-click context menu for art cards. Lightweight — just an absolute
// positioned div that follows the cursor. Closes on any outside click or
// Escape.
function ArtContextMenu({
  x, y, onClose, actions,
}: {
  x: number; y: number; onClose: () => void;
  actions: { label: string; onClick: () => void; danger?: boolean; disabled?: boolean }[];
}) {
  useEffect(() => {
    const handler = () => onClose();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("click", handler);
    window.addEventListener("contextmenu", handler);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("click", handler);
      window.removeEventListener("contextmenu", handler);
      window.removeEventListener("keydown", esc);
    };
  }, [onClose]);
  return (
    <div
      className="context-menu"
      style={{ left: x, top: y }}
      onClick={(e) => e.stopPropagation()}
    >
      {actions.map((a, i) => (
        <button
          key={i}
          className={`context-menu-item ${a.danger ? "danger" : ""}`}
          disabled={a.disabled}
          onClick={() => { a.onClick(); onClose(); }}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}

export function ArtPanel() {
  const { activeId, roster } = useCompanionStore();
  const { history, imageModels, generating, uploading, lastImage,
          fetchHistory, fetchImageModels, generate, uploadArt, deleteArt } = useArtStore();
  const ollama = useStatusStore((s) => s.ollama);
  const showToast = useUIStore((s) => s.showToast);

  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [model, setModel] = useState("x/z-image-turbo");
  const [size, setSize] = useState("1024x1024");
  const [seed, setSeed] = useState<string>("");
  const [steps, setSteps] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [saveNote, setSaveNote] = useState("");
  const [uploadNote, setUploadNote] = useState("");
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; entry: any;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { void fetchImageModels(); }, [fetchImageModels]);
  useEffect(() => { if (activeId) void fetchHistory(activeId); }, [activeId, fetchHistory]);
  useEffect(() => {
    if (imageModels.length > 0 && !imageModels.find((m) => m.name === model)) {
      setModel(imageModels[0].name);
    }
  }, [imageModels, model]);

  if (!activeId) {
    return (
      <div className="empty-state">
        <div className="empty-state-mark">
          <img src="/icons/brand.svg" alt="" width="48" height="48" />
        </div>
        <h2>Pick a companion first</h2>
        <p>Select a companion from the sidebar to generate art together.</p>
      </div>
    );
  }

  const active = roster.find((c) => c.id === activeId);
  const gallery = history[activeId] ?? [];
  const imageGenSupported = ollama?.image_gen_platform_supported ?? true;
  const imageGenReason = ollama?.image_gen_platform_reason ?? null;

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() || generating || !activeId) return;
    setError(null);
    try {
      await generate(activeId, prompt.trim(), {
        model, size,
        seed: seed ? parseInt(seed) : undefined,
        negativePrompt: negativePrompt || undefined,
        steps: steps ? parseInt(steps) : undefined,
      });
      setPrompt("");
    } catch (e) { setError(String(e)); }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !activeId) return;
    setError(null);
    try {
      await uploadArt(activeId, file, uploadNote || prompt || "");
      setUploadNote("");
      showToast("✓ Image added to gallery", "ok");
    } catch (e) {
      setError(String(e));
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Art</h2>
        <p>Generate images with Ollama — or upload your own. Save them as memories and your companion will remember the moment.</p>
      </div>

      {!imageGenSupported && (
        <div className="callout callout-info">
          <div className="callout-icon">✦</div>
          <div className="callout-body">
            <div className="callout-title">AI art via LLM-generated SVG</div>
            <div className="callout-text">
              {imageGenReason
                ? `Ollama native image gen is unavailable on this build (${imageGenReason.split('.')[0]}).`
                : "Ollama native image gen isn't available in this build."}
              {" "}OurNook falls back to asking your LLM to produce vector art — always works, no extra dependencies. Results are unique per prompt.
              {" "}You can also still <strong>upload images</strong> below.
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleGenerate} className="art-form">
        <label>
          <span>Prompt</span>
          <textarea
            placeholder={active ? `Describe what you want to draw with ${active.name}…` : "Describe what you want to draw…"}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            disabled={generating}
          />
        </label>

        <label>
          <span>Negative prompt <span className="dim">(what to avoid)</span></span>
          <input
            placeholder="blurry, low quality, deformed…"
            value={negativePrompt}
            onChange={(e) => setNegativePrompt(e.target.value)}
            disabled={generating}
          />
        </label>

        <div className="art-form-grid">
          <label>
            <span>Model</span>
            <select value={model} onChange={(e) => setModel(e.target.value)} disabled={generating}>
              {imageModels.length === 0 ? (
                <option value="x/z-image-turbo">x/z-image-turbo (default)</option>
              ) : imageModels.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
            </select>
          </label>
          <label>
            <span>Size</span>
            <select value={size} onChange={(e) => setSize(e.target.value)} disabled={generating}>
              {SIZES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </label>
          <label>
            <span>Seed <span className="dim">(optional, for reproducibility)</span></span>
            <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="random" disabled={generating} />
          </label>
          <label>
            <span>Steps <span className="dim">(optional, model default if blank)</span></span>
            <input type="number" value={steps} onChange={(e) => setSteps(e.target.value)} placeholder="auto" disabled={generating} />
          </label>
        </div>

        <div className="row">
          <button type="submit" className="primary" disabled={generating || !prompt.trim()}>
            {generating ? <><span className="spinner" /> Generating…</> : "🎨 Generate"}
          </button>
          <span className="caption dim">or</span>
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            {uploading ? <><span className="spinner" /> Uploading…</> : <>📤 Upload image</>}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
            onChange={handleUpload}
            style={{ display: "none" }}
          />
          {error && <span className="caption danger">✗ {error}</span>}
        </div>
      </form>

      {lastImage && lastImage.companion === activeId && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <div>
              <div className="card-title">Just generated</div>
              <div className="card-subtitle">Make it a moment your companion will remember.</div>
            </div>
          </div>
          <img src={lastImage.url} alt="generated" className="art-preview-img" />
          <div className="row art-remember-row">
            <input
              placeholder="Add a note (optional) — e.g. 'the night we met'"
              value={saveNote}
              onChange={(e) => setSaveNote(e.target.value)}
              className="grow"
            />
            <button
              className="primary"
              onClick={async () => {
                const latest = gallery[0];
                if (!latest) { showToast("Generate or upload an image first", "err"); return; }
                try {
                  await fetch("/api/art/" + latest.id + "/remember", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ companion_id: activeId, note: saveNote || null }),
                  }).then((r) => { if (!r.ok) throw new Error(`remember: ${r.status}`); });
                  showToast("✓ Saved as a shared moment", "ok");
                  setSaveNote("");
                } catch (e) { showToast(`✗ ${e}`, "err"); }
              }}
            >
              🧠 remember this
            </button>
          </div>
        </div>
      )}

      <div className="section">
        <div className="section-title">
          <h3>Gallery</h3>
          <span className="caption">{gallery.length} {gallery.length === 1 ? "image" : "images"}</span>
        </div>

        {gallery.length === 0 ? (
          <div className="empty-state empty-state-narrow">
            <div className="empty-state-mark">
              <img src="/icons/brand.svg" alt="" width="40" height="40" />
            </div>
            <h2>No art yet</h2>
            <p>Generate your first image — or upload one from your computer. Either way, your companion can remember it as a shared moment.</p>
          </div>
        ) : (
          <div className="art-gallery">
            {gallery.map((entry) => (
              <div
                key={entry.id}
                className="art-card"
                onContextMenu={(e) => {
                  e.preventDefault();
                  setContextMenu({ x: e.clientX, y: e.clientY, entry });
                }}
              >
                <img
                  src={`/api/art/${entry.id}/image?companion_id=${activeId}`}
                  alt={entry.prompt}
                  loading="lazy"
                  onError={(e) => {
                    // Some test uploads are 1x1 placeholders; mark them
                    // so the user can see they have nothing to display.
                    const t = e.currentTarget;
                    t.style.opacity = "0.3";
                    t.title = "Image file is empty or unreadable";
                  }}
                />
                <div className="art-card-meta">
                  <div className="art-prompt" title={entry.prompt}>{entry.prompt}</div>
                  <div className="art-info">
                    <span className="tag">{entry.model.split("/").pop()}</span>
                    {entry.width && entry.height && <span className="tag">{entry.width}×{entry.height}</span>}
                    {entry.seed != null && <span className="tag">seed {entry.seed}</span>}
                  </div>
                  <div className="art-info">
                    <span className="caption dim">{new Date(entry.created_at).toLocaleString()}</span>
                  </div>
                  <div className="row art-card-actions">
                    <button
                      onClick={async () => {
                        try {
                          await fetch("/api/art/" + entry.id + "/remember", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ companion_id: activeId, note: null }),
                          }).then((r) => { if (!r.ok) throw new Error(`remember: ${r.status}`); });
                          showToast("✓ Saved as a shared moment", "ok");
                        } catch (e) { showToast(`✗ ${e}`, "err"); }
                      }}
                    >
                      🧠 remember
                    </button>
                    <button className="danger" onClick={() => deleteArt(entry.id).then(() => fetchHistory(activeId))}>
                      delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {contextMenu && (
        <ArtContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          actions={[
            {
              label: "👁  View full size",
              onClick: () => {
                const url = `/api/art/${contextMenu.entry.id}/image?companion_id=${activeId}`;
                window.open(url, "_blank");
              },
            },
            {
              label: "📂  Reveal in Finder",
              onClick: async () => {
                try {
                  const r = await fetch(
                    `/api/art/${contextMenu.entry.id}/reveal?companion_id=${activeId}`,
                    { method: "POST" }
                  );
                  if (!r.ok) throw new Error(`reveal: ${r.status}`);
                } catch (e) { showToast(`✗ ${e}`, "err"); }
              },
            },
            {
              label: "↗  Open in default viewer",
              onClick: async () => {
                try {
                  const r = await fetch(
                    `/api/art/${contextMenu.entry.id}/open?companion_id=${activeId}`,
                    { method: "POST" }
                  );
                  if (!r.ok) throw new Error(`open: ${r.status}`);
                } catch (e) { showToast(`✗ ${e}`, "err"); }
              },
            },
            {
              label: "📋  Copy file path",
              onClick: async () => {
                try {
                  const r = await fetch(
                    `/api/art/${contextMenu.entry.id}/path?companion_id=${activeId}`
                  );
                  if (!r.ok) throw new Error(`path: ${r.status}`);
                  const data = await r.json();
                  await navigator.clipboard.writeText(data.file_path);
                  showToast("✓ Path copied to clipboard", "ok");
                } catch (e) { showToast(`✗ ${e}`, "err"); }
              },
            },
            { label: "─────────", onClick: () => {}, disabled: true },
            {
              label: "🧠 remember as shared moment",
              onClick: async () => {
                try {
                  const r = await fetch("/api/art/" + contextMenu.entry.id + "/remember", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ companion_id: activeId, note: null }),
                  });
                  if (!r.ok) throw new Error(`remember: ${r.status}`);
                  showToast("✓ Saved as a shared moment", "ok");
                } catch (e) { showToast(`✗ ${e}`, "err"); }
              },
            },
            {
              label: "🗑  Delete",
              danger: true,
              onClick: () => {
                if (confirm("Delete this art? It will be removed from the gallery.")) {
                  deleteArt(contextMenu.entry.id).then(() => {
                    fetchHistory(activeId);
                    showToast("✓ Deleted", "ok");
                  });
                }
              },
            },
          ]}
        />
      )}
    </div>
  );
}
