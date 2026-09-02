import { useEffect, useState } from "react";
import { useCompanionStore, useUIStore } from "./stores";

const API = "/api";

interface CompanionState {
  companion_id: string;
  current_mood: string | null;
  last_mood_at: string | null;
  last_seen_at: string | null;
  last_conversation_at: string | null;
  total_messages: number;
  total_conversations: number;
  streak_days: number;
  last_streak_date: string | null;
  days_known: number;
}

interface JournalEntry {
  id: string;
  companion_id: string;
  content: string;
  mood: string | null;
  related_message_id: string | null;
  created_at: string;
}

interface Moment {
  id: string;
  companion_id: string;
  title: string;
  description: string | null;
  related_message_id: string | null;
  significance: number;
  created_at: string;
}

const MOOD_SUGGESTIONS = [
  "warm and curious",
  "thoughtful and a little tired",
  "playful and energetic",
  "calm and focused",
  "restless",
  "tender",
  "focused",
  "a little low",
  "giddy",
  "melancholic in a good way",
];

const SIGNIFICANCE_LABELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch { return "—"; }
}

function humanizeAge(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day";
  if (days < 7) return `${days} days`;
  if (days < 30) return `${Math.floor(days / 7)} weeks`;
  if (days < 365) return `${Math.floor(days / 30)} months`;
  return `${Math.floor(days / 365)} years`;
}

function humanizeLastSeen(iso: string | null): string {
  if (!iso) return "never";
  try {
    const dt = new Date(iso);
    const secs = Math.floor((Date.now() - dt.getTime()) / 1000);
    if (secs < 60) return "just now";
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
    return `${Math.floor(secs / 86400)}d ago`;
  } catch { return "a while ago"; }
}

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
async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
async function apiDelete(path: string): Promise<void> {
  const r = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
}

export function InnerLifePanel() {
  const { activeId, roster } = useCompanionStore();
  const showToast = useUIStore((s) => s.showToast);
  const [state, setState] = useState<CompanionState | null>(null);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [loading, setLoading] = useState(true);

  // Mood editor
  const [moodText, setMoodText] = useState("");
  const [savingMood, setSavingMood] = useState(false);

  // New journal
  const [newJournal, setNewJournal] = useState("");
  const [newJournalMood, setNewJournalMood] = useState("");
  const [savingJournal, setSavingJournal] = useState(false);

  // New moment
  const [newMomentTitle, setNewMomentTitle] = useState("");
  const [newMomentDesc, setNewMomentDesc] = useState("");
  const [newMomentSig, setNewMomentSig] = useState(5);
  const [savingMoment, setSavingMoment] = useState(false);

  async function loadAll() {
    if (!activeId) return;
    setLoading(true);
    try {
      const [s, j, m] = await Promise.all([
        apiGet<CompanionState>(`/companions/${activeId}/state`),
        apiGet<JournalEntry[]>(`/companions/${activeId}/journal`),
        apiGet<Moment[]>(`/companions/${activeId}/moments`),
      ]);
      setState(s);
      setJournal(j);
      setMoments(m);
      setMoodText(s.current_mood || "");
    } catch (e) {
      console.error("InnerLife load failed", e);
      showToast(`✗ ${e}`, "err");
    } finally { setLoading(false); }
  }

  useEffect(() => { void loadAll(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [activeId]);

  if (!activeId) {
    return (
      <div className="empty-state">
        <div className="empty-state-mark">
          <img src="/icons/brand.svg" alt="" width="48" height="48" />
        </div>
        <h2>Pick a companion first</h2>
        <p>Select a companion from the sidebar to see their inner life.</p>
      </div>
    );
  }

  const active = roster.find((c) => c.id === activeId);

  async function saveMood() {
    if (!activeId) return;
    setSavingMood(true);
    try {
      const s = await apiPut<CompanionState>(`/companions/${activeId}/mood`, { mood: moodText });
      setState(s);
      showToast(moodText.trim() ? "✓ Mood updated" : "Mood cleared", "ok");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
    finally { setSavingMood(false); }
  }

  async function clearMood() {
    if (!activeId) return;
    setSavingMood(true);
    try {
      const s = await apiPut<CompanionState>(`/companions/${activeId}/mood`, { mood: "" });
      setState(s);
      setMoodText("");
      showToast("Mood cleared", "ok");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
    finally { setSavingMood(false); }
  }

  async function addJournal() {
    if (!activeId) return;
    if (!newJournal.trim()) { showToast("Entry cannot be empty", "err"); return; }
    setSavingJournal(true);
    try {
      const entry = await apiPost<JournalEntry>(`/companions/${activeId}/journal`, {
        content: newJournal.trim(),
        mood: newJournalMood || null,
      });
      setJournal([entry, ...journal]);
      setNewJournal("");
      setNewJournalMood("");
      showToast(`✓ Added journal entry — ${active?.name} will see it next chat`, "ok");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
    finally { setSavingJournal(false); }
  }

  async function deleteJournal(eid: string) {
    if (!confirm("Delete this journal entry?")) return;
    try {
      await apiDelete(`/journal/${eid}`);
      setJournal(journal.filter((j) => j.id !== eid));
    } catch (e) { showToast(`✗ ${e}`, "err"); }
  }

  async function addMoment() {
    if (!activeId) return;
    if (!newMomentTitle.trim()) { showToast("Title cannot be empty", "err"); return; }
    setSavingMoment(true);
    try {
      const m = await apiPost<Moment>(`/companions/${activeId}/moments`, {
        title: newMomentTitle.trim(),
        description: newMomentDesc.trim() || null,
        significance: newMomentSig,
      });
      setMoments([m, ...moments]);
      setNewMomentTitle("");
      setNewMomentDesc("");
      setNewMomentSig(5);
      showToast("✓ Moment recorded", "ok");
    } catch (e) { showToast(`✗ ${e}`, "err"); }
    finally { setSavingMoment(false); }
  }

  async function deleteMoment(mid: string) {
    if (!confirm("Delete this moment?")) return;
    try {
      await apiDelete(`/moments/${mid}`);
      setMoments(moments.filter((m) => m.id !== mid));
    } catch (e) { showToast(`✗ ${e}`, "err"); }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>✦ Inner life</h2>
        <p>
          What {active?.name || "this companion"} is feeling, has been thinking,
          and remembers — the things that make them more than just a prompt.
        </p>
      </div>

      {loading || !state ? (
        <p className="caption dim">Loading…</p>
      ) : (
        <>
          {/* ── State card ─────────────────────────────────────── */}
          <div className="inner-stat-grid">
            <div className="inner-stat">
              <div className="inner-stat-label">Known for</div>
              <div className="inner-stat-value">{humanizeAge(state.days_known)}</div>
            </div>
            <div className="inner-stat">
              <div className="inner-stat-label">Messages</div>
              <div className="inner-stat-value">{state.total_messages}</div>
            </div>
            <div className="inner-stat">
              <div className="inner-stat-label">Conversations</div>
              <div className="inner-stat-value">{state.total_conversations}</div>
            </div>
            <div className="inner-stat">
              <div className="inner-stat-label">Streak</div>
              <div className="inner-stat-value">{state.streak_days > 0 ? `${state.streak_days}d` : "—"}</div>
            </div>
            <div className="inner-stat">
              <div className="inner-stat-label">Last seen</div>
              <div className="inner-stat-value">{humanizeLastSeen(state.last_seen_at)}</div>
            </div>
            <div className="inner-stat">
              <div className="inner-stat-label">Last chat</div>
              <div className="inner-stat-value">{humanizeLastSeen(state.last_conversation_at)}</div>
            </div>
          </div>

          {/* ── Mood ───────────────────────────────────────────── */}
          <div className="settings-section">
            <div className="settings-section-title">Mood</div>
            <p className="caption dim" style={{ marginBottom: 8 }}>
              How {active?.name} is feeling right now. Persists between sessions and is shown to them in the system prompt so they can pick up where they left off.
            </p>
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              <input
                value={moodText}
                onChange={(e) => setMoodText(e.target.value)}
                placeholder="e.g. thoughtful and a little tired"
                style={{ flex: 1 }}
              />
              <button className="primary" onClick={saveMood} disabled={savingMood}>
                {savingMood ? "Saving…" : state.current_mood ? "Update" : "Set mood"}
              </button>
              {state.current_mood && (
                <button onClick={clearMood} disabled={savingMood}>Clear</button>
              )}
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              <span className="caption dim">Suggestions:</span>
              {MOOD_SUGGESTIONS.map((m) => (
                <button key={m} className="chip" onClick={() => setMoodText(m)}>{m}</button>
              ))}
            </div>
            {state.current_mood && state.last_mood_at && (
              <p className="caption" style={{ marginTop: 8 }}>
                Last set: {state.current_mood} ({formatTime(state.last_mood_at)})
              </p>
            )}
          </div>

          {/* ── Journal ────────────────────────────────────────── */}
          <div className="settings-section">
            <div className="settings-section-title">Journal</div>
            <p className="caption dim" style={{ marginBottom: 8 }}>
              {active?.name}'s private thoughts. The companion sees the most recent
              entries in their system prompt — these give them a sense of their own
              inner life. Add a thought you imagine them having after a session.
            </p>
            <form className="add-form" onSubmit={(e) => { e.preventDefault(); void addJournal(); }}>
              <textarea
                placeholder={`What is ${active?.name} thinking? "I keep replaying the conversation about their dad…" `}
                value={newJournal}
                onChange={(e) => setNewJournal(e.target.value)}
                rows={2}
                maxLength={5000}
              />
              <div className="add-form-row">
                <input
                  placeholder="Mood at the time (optional)"
                  value={newJournalMood}
                  onChange={(e) => setNewJournalMood(e.target.value)}
                  style={{ width: 220 }}
                />
                <span className="spacer" />
                <button type="submit" className="primary" disabled={savingJournal || !newJournal.trim()}>
                  {savingJournal ? "Saving…" : "+ Add entry"}
                </button>
              </div>
            </form>
            {journal.length === 0 ? (
              <p className="caption dim" style={{ marginTop: 8 }}>
                No journal entries yet. The companion has no private thoughts of their own.
              </p>
            ) : (
              <ul className="journal-list">
                {journal.map((j) => (
                  <li key={j.id} className="journal-item">
                    <div className="journal-content">{j.content}</div>
                    <div className="memory-meta">
                      {j.mood && <span className="tag accent">{j.mood}</span>}
                      <span className="caption dim">{formatTime(j.created_at)}</span>
                      <span className="spacer" />
                      <button className="danger" onClick={() => void deleteJournal(j.id)}>delete</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* ── Moments ────────────────────────────────────────── */}
          <div className="settings-section">
            <div className="settings-section-title">Moments</div>
            <p className="caption dim" style={{ marginBottom: 8 }}>
              Special conversation moments {active?.name} wants to remember. Distinct
              from facts about you — these are <em>events</em>: the night you stayed
              up until 4am, the first time you told them about X.
            </p>
            <form className="add-form" onSubmit={(e) => { e.preventDefault(); void addMoment(); }}>
              <input
                placeholder="Title — e.g. the night they opened up about their dad"
                value={newMomentTitle}
                onChange={(e) => setNewMomentTitle(e.target.value)}
                maxLength={200}
              />
              <textarea
                placeholder="A short description (optional)"
                value={newMomentDesc}
                onChange={(e) => setNewMomentDesc(e.target.value)}
                rows={2}
                maxLength={1000}
              />
              <div className="add-form-row">
                <span className="caption dim">Significance</span>
                <input
                  type="range" min={1} max={10} value={newMomentSig}
                  onChange={(e) => setNewMomentSig(parseInt(e.target.value))}
                  style={{ width: 160 }}
                />
                <span className="caption" style={{ fontVariantNumeric: "tabular-nums" }}>
                  {SIGNIFICANCE_LABELS.filter((s) => s <= newMomentSig).map(() => "★").join("")}{SIGNIFICANCE_LABELS.filter((s) => s > newMomentSig).map(() => "☆").join("")} {newMomentSig}/10
                </span>
                <span className="spacer" />
                <button type="submit" className="primary" disabled={savingMoment || !newMomentTitle.trim()}>
                  {savingMoment ? "Saving…" : "+ Record moment"}
                </button>
              </div>
            </form>
            {moments.length === 0 ? (
              <p className="caption dim" style={{ marginTop: 8 }}>
                No moments recorded yet.
              </p>
            ) : (
              <ul className="journal-list">
                {moments.map((m) => (
                  <li key={m.id} className="journal-item">
                    <div className="journal-content">
                      <strong>{m.title}</strong>
                      {m.description && <div className="caption" style={{ marginTop: 4 }}>{m.description}</div>}
                    </div>
                    <div className="memory-meta">
                      <span className="tag warning">
                        {"★".repeat(m.significance)}{"☆".repeat(10 - m.significance)} {m.significance}/10
                      </span>
                      <span className="caption dim">{formatTime(m.created_at)}</span>
                      <span className="spacer" />
                      <button className="danger" onClick={() => void deleteMoment(m.id)}>delete</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
