import { useEffect, useState, useRef } from "react";
import {
  type ImageGenResult,
  type Message,
  useArtStore,
  useChatStore,
  useCompanionStore,
  useMemoryStore,
  useUIStore,
} from "./stores";

const API = "/api";
async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

const MEMORY_CATEGORIES = ["personal", "work", "family", "hobby", "preference", "goal", "emotion", "other"];

const AVATAR_COLORS: Record<string, string> = {
  mira:  "linear-gradient(135deg, #b87fd4, #7f6ed4)",
  sable: "linear-gradient(135deg, #5a7a6a, #3d5a4a)",
  finn:  "linear-gradient(135deg, #7a9abf, #4a7a9a)",
};
function getAvatarStyle(avatarPath: string | null, name: string): React.CSSProperties {
  if (avatarPath && avatarPath.startsWith("bundled:")) {
    const key = avatarPath.replace("bundled:", "");
    return { background: AVATAR_COLORS[key] || "linear-gradient(135deg, #c8a4f0, #f0a4c0)" };
  }
  const hue = (name.charCodeAt(0) * 137) % 360;
  return { background: `linear-gradient(135deg, hsl(${hue}, 55%, 50%), hsl(${(hue + 40) % 360}, 45%, 38%))` };
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " · " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDayHeader(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

function ImportanceStars({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  const interactive = !!onChange;
  return (
    <div className="importance-stars" role={interactive ? "radiogroup" : undefined} aria-label="Importance 1 to 10">
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
        const filled = n <= value;
        return (
          <button
            key={n}
            type="button"
            className={`importance-star ${filled ? "filled" : ""}`}
            onClick={() => onChange?.(n)}
            disabled={!interactive}
            title={interactive ? `Set importance to ${n}` : `Importance ${n}/10`}
            aria-checked={value === n}
            role={interactive ? "radio" : undefined}
          >
            {filled ? "★" : "☆"}
          </button>
        );
      })}
    </div>
  );
}

export function ChatPanel() {
  const { activeId, roster } = useCompanionStore();
  const {
    messagesByCompanion, fetchHistory, send, sending,
    regenerate, deleteMessage, editAndResend,
    interact, rememberMessage, rememberMessageAsDiary, drawLastMoment,
    lastMeta,
  } = useChatStore();
  const { semantic, fetchAll, loadCategoryCounts } = useMemoryStore();
  const { fetchHistory: fetchArt } = useArtStore();
  const showToast = useUIStore((s) => s.showToast);
  const setTab = useUIStore((s) => s.setTab);
  const openEditor = useUIStore((s) => s.openEditor);

  const [showSoul, setShowSoul] = useState(false);
  const [soulText, setSoulText] = useState("");
  const [companionMood, setCompanionMood] = useState<string | null>(null);
  const [rememberingId, setRememberingId] = useState<string | null>(null);
  const [remCat, setRemCat] = useState("emotion");
  const [remImportance, setRemImportance] = useState(6);
  const [remNote, setRemNote] = useState("");
  const [drawing, setDrawing] = useState(false);
  const [savingDiary, setSavingDiary] = useState(false);
  const [inlineArt, setInlineArt] = useState<{ url: string; prompt: string; id: string } | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [draft, setDraft] = useState("");

  const composerRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messages = activeId ? (messagesByCompanion[activeId] ?? []) : [];
  const active = roster.find((c) => c.id === activeId);
  const memories = activeId ? (semantic[activeId] ?? []) : [];
  const topMemories = [...memories].sort((a, b) => b.importance - a.importance).slice(0, 4);

  useEffect(() => {
    if (activeId) {
      setHistoryLoaded(false);
      void fetchHistory(activeId).then(() => setHistoryLoaded(true));
    }
  }, [activeId, fetchHistory]);

  useEffect(() => {
    if (activeId) {
      void fetchAll(activeId);
      void loadCategoryCounts(activeId);
    }
  }, [activeId, fetchAll, loadCategoryCounts]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, sending]);

  useEffect(() => {
    setInlineArt(null);
    setSoulText("");
    setRememberingId(null);
    setRemNote("");
    setHistoryLoaded(false);
    setEditingId(null);
    setEditText("");
    setDraft("");
    if (composerRef.current) composerRef.current.style.height = "auto";
  }, [activeId]);

  useEffect(() => {
    if (showSoul && activeId && soulText === "") {
      apiGet<{ markdown: string }>(`/soul/${activeId}`)
        .then((r) => setSoulText(r.markdown))
        .catch((e) => { showToast(`Could not read soul: ${e}`, "err"); setShowSoul(false); });
    }
  }, [showSoul, activeId, soulText, showToast]);

  // Fetch the companion's current mood so the chat header can show
  // "feeling thoughtful and a little tired" — their inner-life state.
  useEffect(() => {
    if (!activeId) { setCompanionMood(null); return; }
    apiGet<{ current_mood: string | null }>(`/companions/${activeId}/state`)
      .then((s) => setCompanionMood(s.current_mood))
      .catch(() => { /* silent — mood is a nice-to-have */ });
  }, [activeId]);

  if (!activeId || !active) {
    return (
      <div className="chat-area">
        <div className="empty-state">
          <div className="empty-state-mark">
            <img src="/icons/brand.svg" alt="" width="48" height="48" />
          </div>
          <h2>Your companions are waiting</h2>
          <p>Select a companion from the sidebar, or create a new one to begin a conversation.</p>
          <div className="empty-state-cta">
            <button className="primary" onClick={() => useUIStore.getState().openWizard()}>
              ✦ New companion
            </button>
          </div>
        </div>
      </div>
    );
  }

  const tagline = (active.personality || "").trim();
  const avatarStyle = getAvatarStyle(active.avatar_path, active.name);
  const initial = active.name.slice(0, 1).toUpperCase();

  // Build day-divided message list
  const dayBuckets: { day: string; msgs: Message[] }[] = [];
  for (const m of messages) {
    const day = new Date(m.created_at).toDateString();
    const last = dayBuckets[dayBuckets.length - 1];
    if (last && last.day === day) last.msgs.push(m);
    else dayBuckets.push({ day, msgs: [m] });
  }

  // Identify the last assistant + the user message that prompted it,
  // so we can show the regenerate button and the response-time footer.
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const meta = activeId ? lastMeta[activeId] : null;

  function sendDraft() {
    const text = draft.trim();
    if (!text || sending || !activeId) return;
    setDraft("");
    if (composerRef.current) {
      composerRef.current.style.height = "auto";
    }
    void send(activeId, text);
  }

  function onComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter = send. Shift+Enter / Cmd+Enter / Ctrl+Enter = newline.
    // Standard chat-app behaviour: type freely, hit Enter to send.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      sendDraft();
    }
  }

  function onComposerInput(e: React.FormEvent<HTMLTextAreaElement>) {
    const t = e.currentTarget;
    setDraft(t.value);
    // Auto-grow: shrink to one line, then grow with content (capped at ~8 lines)
    t.style.height = "auto";
    const maxH = 8 * 22; // ~8 lines
    t.style.height = Math.min(t.scrollHeight, maxH) + "px";
  }

  async function handleDrawLast() {
    if (!activeId || drawing) return;
    setDrawing(true);
    try {
      const result: ImageGenResult | null = await drawLastMoment(activeId);
      if (result) {
        setInlineArt({ url: `data:image/png;base64,${result.base64}`, prompt: result.id, id: result.id });
        showToast("🎨 Drew this moment", "ok");
        void fetchArt(activeId);
      } else {
        showToast("Send a message first", "err");
      }
    } catch (e) { showToast(`✗ ${e}`, "err"); }
    finally { setDrawing(false); }
  }

  async function handleSaveLastAsDiary() {
    if (!activeId || savingDiary) return;
    const msgs = messagesByCompanion[activeId] ?? [];
    const lastAsst = [...msgs].reverse().find((m) => m.role === "assistant");
    const target = lastAsst ?? msgs[msgs.length - 1];
    if (!target) { showToast("Send a message first", "err"); return; }
    setSavingDiary(true);
    try {
      await rememberMessageAsDiary(activeId, target, null);
      showToast("📖 Saved as diary entry", "ok");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
    finally { setSavingDiary(false); }
  }

  async function handleRegenerate() {
    if (!activeId || sending) return;
    try {
      await regenerate(activeId);
      showToast("↻ Regenerated", "ok");
    } catch (e) {
      showToast(`✗ ${e}`, "err");
    }
  }

  async function handleDeleteMessage(mid: string) {
    if (!activeId) return;
    if (!confirm("Delete this message? This cannot be undone.")) return;
    try {
      await deleteMessage(activeId, mid);
    } catch (e) { showToast(`✗ ${e}`, "err"); }
  }

  function startEditUser(m: Message) {
    setEditingId(m.id);
    setEditText(m.content);
  }

  async function commitEdit(m: Message) {
    if (!activeId) return;
    const text = editText.trim();
    if (!text) { showToast("Message cannot be empty", "err"); return; }
    if (text === m.content) { setEditingId(null); return; }
    try {
      await editAndResend(activeId, m.id, text);
      setEditingId(null);
      showToast("✓ Edited + regenerated", "ok");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      showToast("📋 Copied to clipboard", "ok");
    } catch {
      // Fallback for non-secure contexts
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showToast("📋 Copied", "ok");
    }
  }

  async function commitRemember(msg: Message) {
    if (!activeId || !active) return;
    try {
      await rememberMessage(activeId, msg, remCat, remImportance, remNote || null);
      showToast(`✓ ${active.name} will remember this`, "ok");
      setRememberingId(null);
      setRemNote("");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
  }

  function exportChat() {
    const fmt = activeId ? prompt("Export format — type 'md' or 'txt':", "md") : null;
    if (!fmt || !activeId) return;
    const url = `/api/chat/${activeId}/export?format=${fmt.trim().toLowerCase() === "txt" ? "txt" : "md"}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(active?.name || "companion").replace(/[^A-Za-z0-9_-]+/g, "_")}-chat.${fmt.trim().toLowerCase() === "txt" ? "txt" : "md"}`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  return (
    <div className="chat-area">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-main">
          {active.avatar_path?.endsWith(".png") ? (
            <img className="chat-avatar" src={`/api/avatar/${activeId}?t=${Date.now()}`} alt={active.name} />
          ) : (
            <div className="chat-avatar-initials" style={avatarStyle}>{initial}</div>
          )}
          <div className="chat-header-info">
            <div className="chat-header-name">
              <h2>{active.name}</h2>
              <span className="chat-header-status">
                <span className="dot ok" /> online
              </span>
            </div>
            {tagline && <div className="soul-tagline">{tagline}</div>}
            <div className="chat-header-meta">
              {active.relationship_type} · {active.memory_mode} memory
              {companionMood && (
                <span className="chat-header-mood" title={`Mood: ${companionMood}`}>
                  · feeling <em>{companionMood}</em>
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="chat-header-actions">
          <button className="ghost" onClick={() => setShowSoul(true)} title="View their soul">
            ✦ Soul
          </button>
          <button className="ghost" onClick={exportChat} title="Export chat as Markdown" disabled={messages.length === 0}>
            ⇩ Export
          </button>
          <button className="ghost" onClick={() => openEditor(activeId)} title="Edit this companion">
            ✎ Edit
          </button>
          <button className="ghost" onClick={() => setTab("inner")} title="Inner life: mood, journal, moments">
            ✦ Inner
          </button>
          <button className="ghost" onClick={() => setTab("memory")} title="Open memories">
            🧠 {memories.length}
          </button>
        </div>
      </div>

      {/* Memory chips */}
      {topMemories.length > 0 && (
        <div className="memory-chips">
          <span className="memory-chips-label">remembers</span>
          {topMemories.map((m) => (
            <button key={m.id} className="memory-chip" onClick={() => setTab("memory")} title={m.fact_text}>
              {m.importance >= 10 && <span className="star">★</span>}
              {m.fact_text.length > 70 ? m.fact_text.slice(0, 70) + "…" : m.fact_text}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="messages">
        {!historyLoaded && activeId ? (
          <div className="col" style={{ padding: "40px 0", gap: 12 }}>
            {[1, 2, 3].map((i) => (
              <div key={i} className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                <div className="skeleton" style={{ width: 30, height: 30, borderRadius: "50%", flexShrink: 0 }} />
                <div style={{ flex: 1, maxWidth: 480 }}>
                  <div className="skeleton skeleton-line medium" />
                  <div className="skeleton skeleton-line long" />
                  <div className="skeleton skeleton-line short" />
                </div>
              </div>
            ))}
          </div>
        ) : messages.length === 0 ? (
          <div className="empty-state" style={{ padding: "60px 40px" }}>
            <div className="empty-state-initial" style={avatarStyle}>{initial}</div>
            <h2>{active.name} is here</h2>
            <p>Say hello. The first conversation is the one that starts the story.</p>
          </div>
        ) : (
          dayBuckets.map((bucket, bi) => (
            <div key={bi} className="col" style={{ gap: 0 }}>
              <div className="message-day-divider">{formatDayHeader(bucket.msgs[0].created_at)}</div>
              {bucket.msgs.map((m) => {
                const cleanContent = m.content.replace(/\n*---meta:.*?---/g, "").trimEnd();
                const isLastAssistant = m === lastAssistant;
                return (
                  <div
                    key={m.id}
                    className={`message ${m.role === "assistant" ? "companion" : m.role === "system" ? "system" : "user"}`}
                  >
                    {m.role === "assistant" && (
                      <div className="message-avatar" style={avatarStyle}>{initial}</div>
                    )}
                    <div className="col-sm" style={{ maxWidth: "100%" }}>
                      {editingId === m.id ? (
                        <div className="edit-form" onClick={(e) => e.stopPropagation()}>
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            rows={3}
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                                e.preventDefault();
                                void commitEdit(m);
                              } else if (e.key === "Escape") {
                                setEditingId(null);
                              }
                            }}
                          />
                          <div className="edit-form-actions">
                            <span className="caption">⌘↩ to save · esc to cancel</span>
                            <span className="spacer" />
                            <button onClick={() => setEditingId(null)}>Cancel</button>
                            <button className="primary" onClick={() => void commitEdit(m)}>Save + regenerate</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          {m.role === "assistant" && (
                            <div className="message-meta">
                              <span className="message-sender">{active.name}</span>
                              <span className="message-time">{formatTime(m.created_at)}</span>
                            </div>
                          )}
                          {m.role === "user" && (
                            <div className="message-meta" style={{ justifyContent: "flex-end" }}>
                              <span className="message-time">{formatTime(m.created_at)}</span>
                            </div>
                          )}
                          <div className="message-content">{cleanContent}</div>

                          {/* Per-message actions */}
                          {m.role === "user" && (
                            <div className="message-actions">
                              {rememberingId === m.id ? (
                                <div className="remember-form" onClick={(e) => e.stopPropagation()}>
                                  <select value={remCat} onChange={(e) => setRemCat(e.target.value)}>
                                    {MEMORY_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                                  </select>
                                  <ImportanceStars value={remImportance} onChange={setRemImportance} />
                                  <input type="text" value={remNote} placeholder="why (optional)"
                                    onChange={(e) => setRemNote(e.target.value)}
                                    style={{ flex: 1, minWidth: 100 }} />
                                  <button className="primary" onClick={(e) => { e.stopPropagation(); void commitRemember(m); }}>save</button>
                                  <button onClick={(e) => { e.stopPropagation(); setRememberingId(null); setRemNote(""); }} title="Cancel">×</button>
                                </div>
                              ) : (
                                <button className="msg-action-btn" onClick={(e) => { e.stopPropagation(); setRememberingId(m.id); }} title="Remember this message">
                                  🧠
                                </button>
                              )}
                              <button className="msg-action-btn" onClick={(e) => { e.stopPropagation(); startEditUser(m); }} title="Edit + regenerate from here">
                                ✎
                              </button>
                              <button className="msg-action-btn" onClick={(e) => { e.stopPropagation(); void copyToClipboard(cleanContent); }} title="Copy message">
                                ⧉
                              </button>
                              <button className="msg-action-btn danger" onClick={(e) => { e.stopPropagation(); void handleDeleteMessage(m.id); }} title="Delete message">
                                🗑
                              </button>
                            </div>
                          )}
                          {m.role === "assistant" && (
                            <div className="message-actions">
                              <button className="msg-action-btn" onClick={(e) => { e.stopPropagation(); void copyToClipboard(cleanContent); }} title="Copy message">
                                ⧉
                              </button>
                              {isLastAssistant && (
                                <button className="msg-action-btn" onClick={(e) => { e.stopPropagation(); void handleRegenerate(); }} title="Regenerate this response" disabled={sending}>
                                  ↻
                                </button>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))
        )}

        {/* Response-time footer (right after the last AI message) */}
        {!sending && lastAssistant && meta && meta.ts > new Date(lastAssistant.created_at).getTime() - 5000 && (
          <div className="response-meta">
            <span className="response-meta-model">{meta.model}</span>
            <span className="response-meta-dot">·</span>
            <span className="response-meta-time">{formatDuration(meta.duration_ms)}</span>
            {meta.eval_count != null && (
              <>
                <span className="response-meta-dot">·</span>
                <span className="response-meta-tokens">{meta.eval_count} tokens</span>
              </>
            )}
          </div>
        )}

        {sending && (
          <div className="thinking">
            <div className="message-avatar" style={avatarStyle}>{initial}</div>
            <div className="thinking-bubble">
              <div className="thinking-dot" />
              <div className="thinking-dot" />
              <div className="thinking-dot" />
            </div>
            <button className="ghost stop-generating" onClick={() => showToast("Cancellation coming in v0.12", "ok")} title="Stop generating (coming soon)">
              ■ stop
            </button>
          </div>
        )}

        {inlineArt && (
          <div className="shared-moment">
            <div className="shared-moment-header">
              <span>✨ A moment we shared</span>
              <button className="close-btn" onClick={() => setInlineArt(null)} style={{ width: 22, height: 22, fontSize: 14 }}>×</button>
            </div>
            <img src={inlineArt.url} alt="shared moment" />
            <div className="shared-moment-actions">
              <button
                onClick={async () => {
                  try {
                    await apiPost(`/art/${inlineArt.id}/remember`, { companion_id: activeId, note: null });
                    showToast("✓ Saved as a shared moment", "ok");
                    if (activeId) await useMemoryStore.getState().fetchAll(activeId);
                  } catch (e) { showToast(`✗ ${e}`, "err"); }
                }}
              >
                🧠 remember this
              </button>
              <button className="ghost" onClick={() => setTab("art")}>open in art ↗</button>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick interactions */}
      <div className="avatar-interactions">
        <span className="interactions-label">Quick</span>
        {(["pat", "bonk", "poke", "hug", "wave"] as const).map((kind) => (
          <button key={kind} className="interaction-btn" disabled={sending}
            onClick={() => void interact(activeId, kind)}>
            {kind === "pat" && "🤚 pat"}
            {kind === "bonk" && "🔨 bonk"}
            {kind === "poke" && "👉 poke"}
            {kind === "hug" && "🫂 hug"}
            {kind === "wave" && "👋 wave"}
          </button>
        ))}
        <span className="spacer" />
        <button className="interaction-btn" disabled={drawing || sending || messages.length === 0}
          onClick={() => void handleDrawLast()}>
          {drawing ? <><span className="spinner" /> drawing…</> : "🎨 draw this"}
        </button>
        <button className="interaction-btn" disabled={savingDiary || sending || messages.length === 0}
          onClick={() => void handleSaveLastAsDiary()}>
          {savingDiary ? "saving…" : "📖 save moment"}
        </button>
      </div>

      {/* Composer — multi-line, Enter to send, Shift+Enter for newline */}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); sendDraft(); }}>
        <div className="composer-input-wrap">
          <textarea
            ref={composerRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onInput={onComposerInput}
            onKeyDown={onComposerKeyDown}
            placeholder={`Message ${active.name}…`}
            disabled={sending}
            rows={1}
            className="composer-textarea"
          />
          <div className="composer-hint">
            <span>{draft.length > 0 ? `${draft.length} char${draft.length === 1 ? "" : "s"}` : ""}</span>
            <span className="spacer" />
            <span className="dim">⏎ send · ⇧⏎ newline</span>
          </div>
        </div>
        <button type="submit" className="send-btn" disabled={sending || !draft.trim()} title="Send (Enter)">
          {sending ? <span className="spinner" /> : "→"}
        </button>
      </form>

      {/* Soul modal */}
      {showSoul && (
        <div className="modal-backdrop" onClick={() => setShowSoul(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2><span style={{ filter: "drop-shadow(0 0 6px var(--accent-glow))" }}>✦</span> {active.name}'s soul</h2>
              <button className="close-btn" onClick={() => setShowSoul(false)}>×</button>
            </div>
            <div className="modal-body">
              {soulText ? (
                <pre className="soul-preview">{soulText}</pre>
              ) : (
                <p className="hint">No soul yet. Create a new companion with the wizard to give them a soul.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
