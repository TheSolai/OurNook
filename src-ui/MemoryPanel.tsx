import { useEffect, useState } from "react";
import { useCompanionStore, useMemoryStore } from "./stores";

// v0.15 — Canonical memory categories. The backend's
// api/memory_categories.py owns the source of truth; we mirror it here.
// Order matches the canonical list (used for the filter chips + dropdown).
const CATEGORIES = [
  { id: "identity", name: "Identity" },
  { id: "preferences", name: "Preferences" },
  { id: "history", name: "History" },
  { id: "emotional", name: "Emotional" },
  { id: "projects", name: "Projects" },
  { id: "worldview", name: "Worldview" },
  { id: "inside", name: "Inside" },
];

// Visual star rating for importance (1-10). Renders as a row of 10 stars.
function ImportanceStars({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  const interactive = !!onChange;
  return (
    <div className="importance-stars" role={interactive ? "radiogroup" : undefined}>
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          className={`importance-star ${n <= value ? "filled" : ""}`}
          onClick={() => onChange?.(n)}
          disabled={!interactive}
          title={interactive ? `Importance ${n}/10` : `Importance ${n}/10`}
          aria-checked={value === n}
          role={interactive ? "radio" : undefined}
        >
          {n <= value ? "★" : "☆"}
        </button>
      ))}
    </div>
  );
}

export function MemoryPanel() {
  const { activeId, roster } = useCompanionStore();
  const mem = useMemoryStore();

  const [tab, setTab] = useState<"facts" | "summaries">("facts");
  const [newFact, setNewFact] = useState("");
  const [newCategory, setNewCategory] = useState("identity");
  const [categoryTouched, setCategoryTouched] = useState(false);
  const [newImportance, setNewImportance] = useState(5);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editFact, setEditFact] = useState("");
  const [editCategory, setEditCategory] = useState("personal");
  const [editImportance, setEditImportance] = useState(5);
  const [filterCategory, setFilterCategory] = useState("all");
  const [filterText, setFilterText] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState<string | null>(null);
  const [newSummary, setNewSummary] = useState("");
  const [newTone, setNewTone] = useState("");

  useEffect(() => {
    if (activeId) {
      void mem.fetchAll(activeId);
      void mem.loadCategoryCounts(activeId);
    }
  }, [activeId, mem]);

  if (!activeId) {
    return (
      <div className="empty-state">
        <div className="empty-state-mark">
          <img src="/icons/brand.svg" alt="" width="48" height="48" />
        </div>
        <h2>Pick a companion first</h2>
        <p>Select a companion from the sidebar to view their memories.</p>
      </div>
    );
  }

  const facts = mem.semantic[activeId] ?? [];
  const sums = mem.summaries[activeId] ?? [];
  const active = roster.find((c) => c.id === activeId);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Memory</h2>
        <p>What {active?.name} remembers about you. Stored locally. Survives every restart.</p>
      </div>

      <div className="subtabs">
        <button className={`subtab ${tab === "facts" ? "active" : ""}`} onClick={() => setTab("facts")}>
          🧠 Facts <span className="dim" style={{ marginLeft: 4 }}>· {facts.length}</span>
        </button>
        <button className={`subtab ${tab === "summaries" ? "active" : ""}`} onClick={() => setTab("summaries")}>
          📝 Sessions <span className="dim" style={{ marginLeft: 4 }}>· {sums.length}</span>
        </button>
      </div>

      {/* FACTS */}
      {tab === "facts" && (
        <div className="col-lg">
          <div className="row">
            <button
              className="primary"
              disabled={extracting}
              onClick={async () => {
                setExtracting(true);
                setExtractMsg(null);
                try {
                  const n = await mem.extractFacts(activeId);
                  setExtractMsg(`Extracted ${n} fact${n === 1 ? "" : "s"} from recent chat.`);
                } catch (e) { setExtractMsg(`Failed: ${e}`); }
                finally { setExtracting(false); }
              }}
            >
              {extracting ? <><span className="spinner" /> Thinking…</> : "🧠 Auto-extract from chat"}
            </button>
            {extractMsg && <span className="caption" style={{ marginLeft: 8 }}>{extractMsg}</span>}
          </div>

          <form
            className="add-form"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!newFact.trim()) return;
              await mem.addMemory(activeId, newFact, newCategory, newImportance);
              setNewFact("");
            }}
          >
            <input
              placeholder="Add a fact about the user…"
              value={newFact}
              onChange={(e) => {
                const v = e.target.value;
                setNewFact(v);
                // Auto-suggest a category as the user types. Debounced so we
                // don't spam the API on every keystroke. Only auto-switches
                // the category if the user hasn't already picked one (i.e.
                // it's still the default "identity"). If the user picked
                // something specific, respect that.
                if (v.trim().length >= 8 && newCategory === "identity" && !categoryTouched) {
                  const t = setTimeout(async () => {
                    try {
                      const r = await fetch("/api/memory/suggest-category", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ text: v }),
                      });
                      if (!r.ok) return;
                      const data = await r.json();
                      if (data.category && newCategory === "identity" && !categoryTouched) {
                        setNewCategory(data.category);
                        if (data.importance) setNewImportance(data.importance);
                      }
                    } catch { /* ignore */ }
                  }, 600);
                  return () => clearTimeout(t);
                }
              }}
            />
            <div className="add-form-row" style={{ flexWrap: "wrap" }}>
              <select value={newCategory} onChange={(e) => {
                setNewCategory(e.target.value);
                setCategoryTouched(true);
              }}>
                {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <div className="row" style={{ alignItems: "center", gap: 8 }}>
                <span className="caption dim">Importance</span>
                <ImportanceStars value={newImportance} onChange={setNewImportance} />
                <span className="caption" style={{ fontVariantNumeric: "tabular-nums" }}>{newImportance}/10</span>
              </div>
              <span className="spacer" />
              <button type="submit" className="primary" disabled={!newFact.trim()}>+ Add fact</button>
            </div>
          </form>

          {facts.length > 0 && (
            <div className="row" style={{ flexWrap: "wrap", marginBottom: 4 }}>
              <span className="caption">Filter:</span>
              <button className={`chip ${filterCategory === "all" ? "active" : ""}`} onClick={() => setFilterCategory("all")}
                style={filterCategory === "all" ? { background: "var(--accent-soft)", borderColor: "var(--accent-glow)", color: "var(--accent)" } : {}}>
                all · {facts.length}
              </button>
              {CATEGORIES.map((c) => {
                const count = mem.categoryCounts[c.id] ?? 0;
                if (count === 0) return null;
                return (
                  <button key={c.id} className="chip" onClick={() => setFilterCategory(c.id)}
                    style={filterCategory === c.id ? { background: "var(--accent-soft)", borderColor: "var(--accent-glow)", color: "var(--accent)" } : {}}>
                    {c.name} · {count}
                  </button>
                );
              })}
            </div>
          )}

          {facts.length > 4 && (
            <div className="memory-search">
              <input
                type="search"
                placeholder="Search facts…"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                className="memory-search-input"
              />
            </div>
          )}

          {facts.length === 0 ? (
            <div className="empty-state" style={{ padding: "60px 0", minHeight: 200 }}>
              <div className="empty-state-mark" style={{ width: 56, height: 56, fontSize: 24 }}>🧠</div>
              <h2>No memories yet</h2>
              <p>Auto-extract from chat, or add a fact above. They're injected into every conversation.</p>
            </div>
          ) : facts.filter((m) => filterCategory === "all" || m.category === filterCategory)
                     .filter((m) => !filterText || m.fact_text.toLowerCase().includes(filterText.toLowerCase()))
                     .length === 0 ? (
            <div className="empty-state" style={{ padding: "40px 0", minHeight: 120 }}>
              <p className="caption dim">No memories match your filter.</p>
              <button className="ghost" style={{ marginTop: 8 }} onClick={() => { setFilterText(""); setFilterCategory("all"); }}>
                Clear filters
              </button>
            </div>
          ) : (
            <ul className="memory-list">
              {facts
                .filter((m) => filterCategory === "all" || m.category === filterCategory)
                .filter((m) => !filterText || m.fact_text.toLowerCase().includes(filterText.toLowerCase()))
                .map((m) => (
                  <li key={m.id} className="memory-item">
                    {editingId === m.id ? (
                      <>
                        <textarea value={editFact} onChange={(e) => setEditFact(e.target.value)} rows={2} />
                        <div className="add-form-row" style={{ marginTop: 8, flexWrap: "wrap" }}>
                          <select value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
                            {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                          </select>
                          <div className="row" style={{ alignItems: "center", gap: 8 }}>
                            <span className="caption dim">Importance</span>
                            <ImportanceStars value={editImportance} onChange={setEditImportance} />
                            <span className="caption" style={{ fontVariantNumeric: "tabular-nums" }}>{editImportance}/10</span>
                          </div>
                          <span className="spacer" />
                          <button onClick={() => setEditingId(null)}>Cancel</button>
                          <button className="primary" onClick={async () => {
                            await mem.updateMemory(m.id, editFact, editCategory, editImportance);
                            setEditingId(null);
                            if (activeId) { await mem.fetchAll(activeId); await mem.loadCategoryCounts(activeId); }
                          }}>Save</button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="memory-text">{m.fact_text}</div>
                        <div className="memory-meta">
                          {m.category && <span className="tag accent">{m.category}</span>}
                          <span className="tag warning">★ {m.importance}/10</span>
                          {m.importance >= 10 && <span className="tag warning">identity</span>}
                          <div className="memory-meta-actions">
                            {m.importance < 10 && (
                              <button onClick={async () => {
                                await mem.promoteToIdentity(m.id);
                                if (activeId) await mem.fetchAll(activeId);
                              }} title="Pin as identity — always injected into chat">⬆ pin</button>
                            )}
                            <button onClick={() => {
                              setEditingId(m.id);
                              setEditFact(m.fact_text);
                              setEditCategory(m.category ?? "personal");
                              setEditImportance(m.importance);
                            }}>edit</button>
                            <button className="danger" onClick={async () => {
                              await mem.deleteMemory(m.id);
                              if (activeId) { await mem.fetchAll(activeId); await mem.loadCategoryCounts(activeId); }
                            }}>delete</button>
                          </div>
                        </div>
                      </>
                    )}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}

      {/* SUMMARIES */}
      {tab === "summaries" && (
        <div className="col-lg">
          <form
            className="add-form"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!newSummary.trim()) return;
              await mem.saveSummary(activeId, newSummary, newTone || undefined, undefined);
              setNewSummary("");
              setNewTone("");
            }}
          >
            <textarea
              placeholder="Write a session summary — what happened, in their words…"
              value={newSummary}
              onChange={(e) => setNewSummary(e.target.value)}
              rows={3}
            />
            <div className="add-form-row">
              <input
                placeholder="Emotional tone (optional)"
                value={newTone}
                onChange={(e) => setNewTone(e.target.value)}
              />
              <span className="spacer" />
              <button type="submit" className="primary" disabled={!newSummary.trim()}>+ Save summary</button>
            </div>
          </form>

          {sums.length === 0 ? (
            <div className="empty-state" style={{ padding: "60px 0", minHeight: 200 }}>
              <div className="empty-state-mark" style={{ width: 56, height: 56, fontSize: 22 }}>📝</div>
              <h2>No session summaries yet</h2>
              <p>After meaningful conversations, write a summary. Future chats see it.</p>
            </div>
          ) : (
            <ul className="memory-list">
              {sums.map((s) => (
                <li key={s.id} className="memory-item">
                  <div className="memory-text">{s.summary}</div>
                  <div className="memory-meta">
                    {s.emotional_tone && <span className="tag accent">{s.emotional_tone}</span>}
                    {s.relationship_state && <span className="tag">{s.relationship_state}</span>}
                    <div className="memory-meta-actions">
                      <span className="caption">{new Date(s.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* DIARY — moved to a dedicated DiaryPanel (top-level page). */}
    </div>
  );
}

