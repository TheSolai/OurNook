import { useEffect, useState, useRef } from "react";
import { useCompanionStore, useStatusStore, useUIStore } from "./stores";
import type { EnneagramType } from "./EnneagramStep";

const API = "/api";

const RELATIONSHIPS = ["friend", "mentor", "partner", "rival", "family", "stranger", "custom"];
const MEMORY_MODES = [
  { id: "auto", label: "Auto — companion writes their own notes" },
  { id: "manual", label: "Manual — you write what they remember" },
  { id: "hybrid", label: "Hybrid — both, with your edits" },
];

interface EditableCompanion {
  id: string;
  name: string;
  backstory: string;
  personality: string;
  relationship_type: string;
  memory_mode: string;
  model_name: string;
  voice_config: string | null;
  soul: string;
  enneagram_type: number | null;
  enneagram_wing: number | null;
  enneagram_instinct: string | null;
  enneagram_health: string | null;
}

export function EditCompanionPanel({ companionId, onClose }: { companionId: string; onClose: () => void }) {
  const { fetchRoster } = useCompanionStore();
  const { ollamaModels } = useStatusStore();
  const showToast = useUIStore((s) => s.showToast);

  const [tab, setTab] = useState<"basic" | "soul" | "enneagram">("basic");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [soulSaving, setSoulSaving] = useState(false);
  const [ennSaving, setEnnSaving] = useState(false);
  const [types, setTypes] = useState<Record<number, EnneagramType> | null>(null);
  const [data, setData] = useState<EditableCompanion | null>(null);
  const [original, setOriginal] = useState<EditableCompanion | null>(null);
  const dirty = useRef(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/companions/${companionId}`).then((r) => r.json()),
      fetch(`${API}/soul/${companionId}`).then((r) => r.json()).catch(() => ({ markdown: "" })),
      fetch(`${API}/enneagram/types`).then((r) => r.json()).catch(() => null),
    ])
      .then(([c, soulData, ennTypes]) => {
        const ed: EditableCompanion = {
          id: c.id,
          name: c.name || "",
          backstory: c.backstory || "",
          personality: c.personality || "",
          relationship_type: c.relationship_type || "friend",
          memory_mode: c.memory_mode || "hybrid",
          model_name: c.model_name || "qwen3:14b",
          voice_config: c.voice_config || null,
          soul: soulData.markdown || "",
          enneagram_type: c.enneagram_type ?? null,
          enneagram_wing: c.enneagram_wing ?? null,
          enneagram_instinct: c.enneagram_instinct ?? null,
          enneagram_health: c.enneagram_health ?? null,
        };
        setData(ed);
        setOriginal(ed);
        if (ennTypes) setTypes(ennTypes);
        setLoading(false);
      })
      .catch((e) => {
        showToast(`✗ ${e}`, "err");
        setLoading(false);
      });
  }, [companionId, showToast]);

  // Mark dirty when data changes
  useEffect(() => {
    if (!data || !original) return;
    dirty.current = JSON.stringify(data) !== JSON.stringify(original);
  }, [data, original]);

  function setField<K extends keyof EditableCompanion>(key: K, value: EditableCompanion[K]) {
    if (!data) return;
    setData({ ...data, [key]: value });
  }

  async function saveBasic() {
    if (!data) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/companions/${data.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: data.name,
          backstory: data.backstory,
          personality: data.personality,
          relationship_type: data.relationship_type,
          memory_mode: data.memory_mode,
          model_name: data.model_name,
          voice_config: data.voice_config,
        }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const updated = await r.json();
      // Update data with server response to reset dirty state
      setData({ ...data, ...updated, soul: data.soul });
      setOriginal({ ...data, ...updated, soul: data.soul });
      await fetchRoster();
      showToast("✓ Saved", "ok");
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setSaving(false);
    }
  }

  async function saveSoul() {
    if (!data) return;
    setSoulSaving(true);
    try {
      const r = await fetch(`${API}/companions/${data.id}/soul`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ soul: data.soul }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      setOriginal({ ...data, soul: data.soul });
      showToast("✓ Soul saved", "ok");
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setSoulSaving(false);
    }
  }

  async function saveEnneagram() {
    if (!data) return;
    setEnnSaving(true);
    try {
      const r = await fetch(`${API}/companions/${data.id}/enneagram`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: data.enneagram_type,
          wing: data.enneagram_wing,
          instinct: data.enneagram_instinct,
          health: data.enneagram_health,
        }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      setOriginal({ ...data });
      await fetchRoster();
      showToast("✓ Personality saved", "ok");
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setEnnSaving(false);
    }
  }

  async function regenerateFromType() {
    if (!data || data.enneagram_type === null) return;
    try {
      const r = await fetch(`${API}/enneagram/build-soul`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: data.enneagram_type,
          wing: data.enneagram_wing,
          instinct: data.enneagram_instinct || "sp",
          health: data.enneagram_health || "average",
          name: data.name,
        }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const { soul } = await r.json();
      setData({ ...data, soul });
      // Switch to soul tab so the user sees the new content
      setTab("soul");
      showToast("✓ Soul regenerated from Enneagram", "ok");
    } catch (e) {
      showToast(`✗ ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }

  function parseVoiceConfig(): { voice_id: string; speed: number; pitch: number } {
    if (!data?.voice_config) return { voice_id: "", speed: 1, pitch: 0 };
    try {
      const v = JSON.parse(data.voice_config);
      return {
        voice_id: v.voice_id ?? "",
        speed: typeof v.speed === "number" ? v.speed : 1,
        pitch: typeof v.pitch === "number" ? v.pitch : 0,
      };
    } catch {
      return { voice_id: "", speed: 1, pitch: 0 };
    }
  }

  function setVoiceField(key: "voice_id" | "speed" | "pitch", value: string | number) {
    if (!data) return;
    const v = parseVoiceConfig();
    if (key === "voice_id") v.voice_id = String(value);
    else if (key === "speed") v.speed = Number(value);
    else v.pitch = Number(value);
    setField("voice_config", JSON.stringify(v));
  }

  if (loading || !data) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Edit companion</h2>
            <button className="close-btn" onClick={onClose}>×</button>
          </div>
          <div className="modal-body" style={{ textAlign: "center", padding: "60px 0" }}>
            <span className="spinner" /> Loading…
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wizard" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>✎ Edit · {data.name}</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="subtabs" style={{ padding: "0 16px", background: "var(--bg-2)", borderBottom: "1px solid var(--border-2)" }}>
          <button className={`subtab ${tab === "basic" ? "active" : ""}`} onClick={() => setTab("basic")}>
            Basic
          </button>
          <button className={`subtab ${tab === "enneagram" ? "active" : ""}`} onClick={() => setTab("enneagram")}>
            Enneagram
            {data.enneagram_type && <span className="dim" style={{ marginLeft: 4 }}>· {data.enneagram_type}{data.enneagram_wing ? `w${data.enneagram_wing}` : ""}</span>}
          </button>
          <button className={`subtab ${tab === "soul" ? "active" : ""}`} onClick={() => setTab("soul")}>
            Soul.md {dirty.current && data.soul !== original?.soul && <span className="dot" style={{ background: "var(--warning)", display: "inline-block", width: 6, height: 6, borderRadius: "50%", marginLeft: 6, verticalAlign: "middle" }} />}
          </button>
        </div>

        <div className="modal-body" style={{ maxHeight: "60vh" }}>
          {tab === "basic" ? (
            <div className="col-lg">
              <label>
                <span>Name</span>
                <input
                  value={data.name}
                  onChange={(e) => setField("name", e.target.value)}
                  maxLength={50}
                />
              </label>

              <label>
                <span>Backstory <span className="dim">— who they are, what they've done</span></span>
                <textarea
                  value={data.backstory}
                  onChange={(e) => setField("backstory", e.target.value)}
                  rows={5}
                />
              </label>

              <label>
                <span>Personality <span className="dim">— how they talk, what they're like</span></span>
                <textarea
                  value={data.personality}
                  onChange={(e) => setField("personality", e.target.value)}
                  rows={3}
                />
              </label>

              <div className="art-form-grid">
                <label>
                  <span>Relationship</span>
                  <select
                    value={data.relationship_type}
                    onChange={(e) => setField("relationship_type", e.target.value)}
                  >
                    {RELATIONSHIPS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </label>

                <label>
                  <span>Memory mode</span>
                  <select
                    value={data.memory_mode}
                    onChange={(e) => setField("memory_mode", e.target.value)}
                  >
                    {MEMORY_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </select>
                </label>
              </div>

              <label>
                <span>Model <span className="dim">— which LLM they use for chat</span></span>
                {ollamaModels.length > 0 ? (
                  <select
                    value={data.model_name}
                    onChange={(e) => setField("model_name", e.target.value)}
                  >
                    {!ollamaModels.find((m) => m.name === data.model_name) && (
                      <option value={data.model_name}>{data.model_name} (not installed)</option>
                    )}
                    {ollamaModels.map((m) => (
                      <option key={m.name} value={m.name}>{m.name}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={data.model_name}
                    onChange={(e) => setField("model_name", e.target.value)}
                    placeholder="qwen3:14b"
                  />
                )}
              </label>

              <div className="settings-section-title" style={{ marginTop: 16 }}>Voice <span className="dim" style={{ fontSize: 11, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>— TTS settings, JSON stored</span></div>
              <div className="row" style={{ gap: 8, alignItems: "flex-end" }}>
                <label style={{ flex: 1 }}>
                  <span>Voice ID</span>
                  <input
                    value={parseVoiceConfig().voice_id}
                    onChange={(e) => setVoiceField("voice_id", e.target.value)}
                    placeholder="af_sarah / bm_george / etc"
                  />
                </label>
                <label style={{ width: 100 }}>
                  <span>Speed</span>
                  <input
                    type="number"
                    step="0.1"
                    min="0.5"
                    max="2"
                    value={parseVoiceConfig().speed}
                    onChange={(e) => setVoiceField("speed", parseFloat(e.target.value) || 1)}
                  />
                </label>
                <label style={{ width: 80 }}>
                  <span>Pitch</span>
                  <input
                    type="number"
                    step="0.5"
                    min="-12"
                    max="12"
                    value={parseVoiceConfig().pitch}
                    onChange={(e) => setVoiceField("pitch", parseFloat(e.target.value) || 0)}
                  />
                </label>
              </div>
            </div>
          ) : tab === "enneagram" ? (
            <div className="col">
              <p className="caption" style={{ marginBottom: 12 }}>
                The Enneagram type drives how the companion talks, what they value, and how
                they grow. Pick a type to set their personality, or regenerate the soul from
                the type below.
              </p>
              {!types ? (
                <p>Loading Enneagram types…</p>
              ) : (
                <div className="grid-2" style={{ gap: 8 }}>
                  {Object.entries(types).map(([n, t]) => (
                    <button
                      key={n}
                      className={`archetype-card ${data.enneagram_type === Number(n) ? "active" : ""}`}
                      onClick={() => setData({
                        ...data,
                        enneagram_type: Number(n),
                        enneagram_wing: null,
                      })}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <strong>Type {n}</strong>
                        <span className="dim" style={{ fontSize: 11 }}>{t.triad}</span>
                      </div>
                      <div>{t.name}</div>
                      <div className="dim" style={{ fontSize: 11, marginTop: 2 }}>{t.one_liner}</div>
                    </button>
                  ))}
                </div>
              )}
              {data.enneagram_type !== null && types && types[data.enneagram_type] && (
                <>
                  <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                    <label style={{ flex: 1, minWidth: 140 }}>
                      <span>Wing</span>
                      <select
                        value={data.enneagram_wing ?? ""}
                        onChange={(e) => setData({
                          ...data,
                          enneagram_wing: e.target.value ? Number(e.target.value) : null,
                        })}
                      >
                        <option value="">None</option>
                        {Object.entries(types[data.enneagram_type].wings).map(([w, desc]) => (
                          <option key={w} value={w}>
                            {w} — {desc.split(" — ")[0]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1, minWidth: 140 }}>
                      <span>Instinct</span>
                      <select
                        value={data.enneagram_instinct ?? "sp"}
                        onChange={(e) => setData({ ...data, enneagram_instinct: e.target.value })}
                      >
                        <option value="sp">Self-Preservation (sp)</option>
                        <option value="so">Social (so)</option>
                        <option value="sx">Sexual / One-to-One (sx)</option>
                      </select>
                    </label>
                    <label style={{ flex: 1, minWidth: 140 }}>
                      <span>Health</span>
                      <select
                        value={data.enneagram_health ?? "average"}
                        onChange={(e) => setData({ ...data, enneagram_health: e.target.value })}
                      >
                        <option value="healthy">Healthy — wise, generous</option>
                        <option value="average">Average — typical</option>
                        <option value="unhealthy">Unhealthy — under stress</option>
                      </select>
                    </label>
                  </div>
                  <div className="card" style={{ marginTop: 12, padding: 12, background: "var(--bg-2)", border: "1px solid var(--border-2)", borderRadius: 8 }}>
                    <p className="dim" style={{ fontSize: 12, marginBottom: 4 }}>
                      <strong>Core fear:</strong> {types[data.enneagram_type].core_fear}
                    </p>
                    <p className="dim" style={{ fontSize: 12, marginBottom: 4 }}>
                      <strong>Core desire:</strong> {types[data.enneagram_type].core_desire}
                    </p>
                    <p className="dim" style={{ fontSize: 12 }}>
                      <strong>Communication:</strong> {types[data.enneagram_type].communication.split(".")[0]}.
                    </p>
                  </div>
                  <button
                    onClick={regenerateFromType}
                    style={{ marginTop: 12 }}
                  >
                    ✦ Regenerate soul.md from this Enneagram
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="col">
              <p className="caption" style={{ marginBottom: 8 }}>
                The <code>soul.md</code> is the full character definition injected into every conversation.
                Use Markdown — sections like <code>## Who They Are</code>, <code>## How They Talk</code>, <code>## Contradictions</code> are how OurNook organizes the soul.
              </p>
              <textarea
                value={data.soul}
                onChange={(e) => setField("soul", e.target.value)}
                rows={20}
                style={{
                  fontFamily: "SF Mono, Menlo, Consolas, monospace",
                  fontSize: 12.5,
                  lineHeight: 1.6,
                  minHeight: 360,
                }}
              />
              <div className="row" style={{ marginTop: 4 }}>
                <span className="caption">
                  {data.soul.length} chars · ~{Math.round(data.soul.length / 4)} tokens
                </span>
                <span className="spacer" />
                <span className="caption">
                  Tip: the first line after <code>#</code> is the tagline shown in the chat header.
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button onClick={onClose}>Close</button>
          <span className="spacer" />
          {tab === "basic" ? (
            <button className="primary" onClick={saveBasic} disabled={saving || !dirty.current}>
              {saving ? <><span className="spinner" /> Saving…</> : "Save changes"}
            </button>
          ) : tab === "enneagram" ? (
            <button
              className="primary"
              onClick={saveEnneagram}
              disabled={ennSaving || (
                data.enneagram_type === original?.enneagram_type &&
                data.enneagram_wing === original?.enneagram_wing &&
                data.enneagram_instinct === original?.enneagram_instinct &&
                data.enneagram_health === original?.enneagram_health
              )}
            >
              {ennSaving ? <><span className="spinner" /> Saving…</> : "Save personality"}
            </button>
          ) : (
            <button
              className="primary"
              onClick={saveSoul}
              disabled={soulSaving || data.soul === original?.soul}
            >
              {soulSaving ? <><span className="spinner" /> Saving…</> : "Save soul.md"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
