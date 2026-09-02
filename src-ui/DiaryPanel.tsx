import { useEffect, useState } from "react";
import { useUIStore, useCompanionStore } from "./stores";

const API = "";  // same-origin

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
  if (!r.ok) throw new Error(await r.text() || `${path}: ${r.status}`);
  return r.json();
}
async function apiDelete(path: string): Promise<void> {
  const r = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
}

interface DiaryEntry {
  id: string;
  companion_id: string;
  content: string;
  mood_tag: string | null;
  companion_read_at: string | null;
  created_at: string;
}

const MOODS = ["😊", "🥰", "😌", "🤔", "😢", "😠", "😴", "🤩", "🥺", "😎"];

export function DiaryPanel() {
  const activeId = useCompanionStore((s) => s.activeId);
  const companions = useCompanionStore((s) => s.roster);
  const active = companions.find((c) => c.id === activeId);
  const showToast = useUIStore((s) => s.showToast);

  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [text, setText] = useState("");
  const [mood, setMood] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<"all" | "unread" | "yours">("all");

  // Load entries
  useEffect(() => {
    if (!activeId) return;
    setLoading(true);
    apiGet<DiaryEntry[]>(`/diary/${activeId}`)
      .then((d) => setEntries(d))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [activeId]);

  // Mark unread as read when the panel is opened
  useEffect(() => {
    if (!activeId || entries.length === 0) return;
    const hasUnread = entries.some((e) => !e.companion_read_at);
    if (hasUnread) {
      apiPost(`/companions/${activeId}/diary/mark-read`, {}).catch(() => {});
      // Optimistically mark as read locally
      setEntries((prev) => prev.map((e) => ({ ...e, companion_read_at: e.companion_read_at ?? new Date().toISOString() })));
    }
  }, [activeId, entries.length]);

  if (!activeId || !active) {
    return (
      <div className="panel-empty">
        <div className="empty-state">
          <div className="empty-state-mark">📖</div>
          <h2>No companion selected</h2>
          <p>Pick someone from the sidebar to write in your diary.</p>
        </div>
      </div>
    );
  }

  async function addEntry(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || !activeId) return;
    try {
      const created = await apiPost<DiaryEntry>(`/diary`, {
        companion_id: activeId,
        content: text.trim(),
        mood_tag: mood,
      });
      setEntries([created, ...entries]);
      setText("");
      setMood(null);
      showToast("📖 Diary entry saved", "ok");
    } catch (err) {
      showToast(`Failed to save: ${(err as Error).message}`, "err");
    }
  }

  async function removeEntry(id: string) {
    if (!confirm("Delete this diary entry?")) return;
    try {
      await apiDelete(`/diary/${id}`);
      setEntries(entries.filter((e) => e.id !== id));
    } catch (err) {
      showToast(`Failed to delete: ${(err as Error).message}`, "err");
    }
  }

  // Filter
  const filtered = entries.filter((e) => {
    if (filter === "unread") return !e.companion_read_at;
    if (filter === "yours") return true; // All user entries
    return true;
  });

  const unreadCount = entries.filter((e) => !e.companion_read_at).length;

  return (
    <div className="diary-panel">
      <div className="diary-header">
        <div>
          <h2>📖 Diary · {active.name}</h2>
          <p className="dim" style={{ fontSize: 13, marginTop: 4 }}>
            Your private journal. {active.name} can read these entries to know you better.
          </p>
        </div>
        <div className="diary-stats">
          <div className="diary-stat">
            <div className="diary-stat-num">{entries.length}</div>
            <div className="diary-stat-label">entries</div>
          </div>
          {unreadCount > 0 && (
            <div className="diary-stat" style={{ background: "var(--accent-soft)" }}>
              <div className="diary-stat-num">{unreadCount}</div>
              <div className="diary-stat-label">unread</div>
            </div>
          )}
        </div>
      </div>

      {/* Compose */}
      <form className="diary-compose" onSubmit={addEntry}>
        <textarea
          placeholder={`What's on your mind, ${active.name} should know about?`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
        />
        <div className="diary-compose-row">
          <span className="caption">Mood:</span>
          {MOODS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMood(mood === m ? null : m)}
              className="mood-btn"
              style={mood === m ? { background: "var(--accent-soft)", borderColor: "var(--accent)" } : {}}
            >
              {m}
            </button>
          ))}
          <span style={{ flex: 1 }} />
          <button type="submit" className="primary" disabled={!text.trim()}>
            + Save entry
          </button>
        </div>
      </form>

      {/* Filter */}
      {entries.length > 0 && (
        <div className="diary-filters">
          <button
            className={`chip ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            All ({entries.length})
          </button>
          {unreadCount > 0 && (
            <button
              className={`chip ${filter === "unread" ? "active" : ""}`}
              onClick={() => setFilter("unread")}
            >
              Unread ({unreadCount})
            </button>
          )}
        </div>
      )}

      {/* Entries */}
      {loading ? (
        <div className="empty-state">
          <p>Loading…</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state" style={{ padding: "60px 0", minHeight: 200 }}>
          <div className="empty-state-mark" style={{ width: 56, height: 56, fontSize: 22 }}>📖</div>
          <h2>{filter === "unread" ? "All caught up" : "Your diary is empty"}</h2>
          <p>
            {filter === "unread"
              ? "No unread entries."
              : `Write something for ${active.name} to read and remember.`}
          </p>
        </div>
      ) : (
        <ul className="diary-entries">
          {filtered.map((e) => (
            <li key={e.id} className="diary-entry">
              <div className="diary-entry-header">
                {e.mood_tag && <span className="diary-entry-mood">{e.mood_tag}</span>}
                <span className="caption">
                  {new Date(e.created_at).toLocaleString(undefined, {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                {e.companion_read_at ? (
                  <span className="caption dim" title={`Read by ${active.name} at ${new Date(e.companion_read_at).toLocaleString()}`}>
                    · read by {active.name}
                  </span>
                ) : (
                  <span className="caption" style={{ color: "var(--accent)" }}>· unread</span>
                )}
                <span style={{ flex: 1 }} />
                <button className="danger small" onClick={() => removeEntry(e.id)}>
                  delete
                </button>
              </div>
              <div className="diary-entry-content">{e.content}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
