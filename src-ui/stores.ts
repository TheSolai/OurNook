// stores.ts — OurNook v0.4
// All Tauri invoke() calls replaced with fetch() to the FastAPI backend.
// API base: http://127.0.0.1:18765

import { create } from "zustand";

// ── localStorage persistence helpers ────────────────────────────
const LS_PREFIX = "ournook:";
const lsGet = (key: string): string | null => {
  try { return localStorage.getItem(LS_PREFIX + key); } catch { return null; }
};
const lsSet = (key: string, value: string): void => {
  try { localStorage.setItem(LS_PREFIX + key, value); } catch { /* ignore */ }
};
const lsRemove = (key: string): void => {
  try { localStorage.removeItem(LS_PREFIX + key); } catch { /* ignore */ }
};

// ── FastAPI helper ────────────────────────────────────────────────
const API = "/api";

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return r.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return r.json();
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`);
  return r.json();
}

async function apiDelete(path: string): Promise<void> {
  const r = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
}

// ── Types ─────────────────────────────────────────────────────────

export interface Companion {
  id: string; name: string; avatar_path: string | null;
  backstory: string; personality: string; voice_config: string | null;
  memory_mode: string; model_name: string; relationship_type: string;
  created_at: string; updated_at: string;
}

export interface Message {
  id: string; companion_id: string; role: string;
  content: string; starred: boolean; created_at: string;
}

export interface AppInfo {
  name: string; version: string; platform: string;
  data_dir: string; started_at: string;
}

export interface OllamaHealth {
  healthy: boolean; url: string; error: string | null;
  image_gen_platform_supported: boolean; image_gen_platform_reason: string | null;
}

export interface OllamaModel {
  name: string; size: number; family: string | null;
  parameter_size: string | null; quantization_level: string | null;
}

export interface ChatResult {
  user: Message; assistant: Message; model: string;
  total_duration_ns: number | null; eval_count: number | null;
}

export interface SemanticMemory {
  id: string; companion_id: string; fact_text: string;
  category: string | null; importance: number; created_at: string;
}

export interface SessionSummary {
  id: string; companion_id: string; summary: string;
  emotional_tone: string | null; relationship_state: string | null; created_at: string;
}

export interface DiaryEntry {
  id: string; companion_id: string; content: string;
  mood_tag: string | null; companion_read_at: string | null; created_at: string;
}

export interface ArtEntry {
  id: string; companion_id: string; prompt: string;
  negative_prompt: string | null; model: string; seed: number | null;
  width: number; height: number; steps: number | null;
  file_path: string; created_at: string;
}

export interface ImageGenResult {
  id: string; file_path: string; base64: string; model: string;
  seed: number | null; width: number; height: number; duration_ms: number;
}

export interface ExtractedFact { fact: string; category: string | null; importance: number; }

export interface QuizConstants {
  questions: Array<{ id: string; trait_letter: string; text: string; reverse: boolean }>;
  archetypes: Array<{ id: string; label: string }>;
  pronouns: Array<{ id: string; label: string }>;
  age_brackets: Array<{ id: string; label: string }>;
  voice_packs: Array<{ id: string; name: string; language: string; gender: string }>;
}

export interface OceanTraits {
  openness: number; conscientiousness: number;
  extraversion: number; agreeableness: number; neuroticism: number;
}

export interface GeneratedSoul {
  markdown: string; tagline: string; contradictions: string[];
  coping_mechanism: string; current_struggle: string; growth_arc: string;
}

export interface BackupFileInfo {
  path: string; name: string; bytes: number; modified: number;
}

export interface AvatarResult {
  file_path: string; base64: string; model: string;
  seed: number | null; width: number; height: number; duration_ms: number;
  kind?: "png" | "svg";
}

export interface QuizAnswer {
  question_id: string; value: number;
}

export interface SoulInputs {
  identity: { name: string; pronouns: string; age_bracket: string; hook?: string | null };
  archetype: string; ocean: OceanTraits;
  quiz_answers: QuizAnswer[]; freeform_notes?: string | null;
  voice: { voice_id: string; speed: number; pitch: number; description: string };
}

export interface ModelInfo {
  name: string; category: string; label: string; description: string;
  size: string; ram_needed: string; gpu: string; pull_cmd: string;
  url: string; why: string; tags: string[];
  installed: boolean; installed_size?: number;
}

// ── Companion store ────────────────────────────────────────────────

interface CompanionStoreState {
  roster: Companion[]; activeId: string | null; loading: boolean;
  fetchRoster: () => Promise<void>; setActive: (id: string | null) => void;
  create: (name: string, backstory: string, personality: string) => Promise<Companion>;
  update: (id: string, fields: Partial<Companion>) => Promise<Companion>;
  updateSoul: (id: string, soul: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useCompanionStore = create<CompanionStoreState>((set) => ({
  roster: [], activeId: lsGet("activeCompanionId"), loading: false,

  fetchRoster: async () => {
    set({ loading: true });
    try {
      const roster = await apiGet<Companion[]>("/companions");
      // Prefer the persisted activeId; if it's gone (deleted, etc.) fall back
      // to the first companion so the UI isn't blank.
      const persisted = lsGet("activeCompanionId");
      const stillExists = persisted && roster.find((c) => c.id === persisted);
      set((s) => ({
        roster, loading: false,
        activeId: stillExists ? persisted : (s.activeId && roster.find((c) => c.id === s.activeId)
          ? s.activeId : roster[0]?.id ?? null),
      }));
      // Persist the resolved activeId (in case we fell back)
      const finalId = useCompanionStore.getState().activeId;
      if (finalId) lsSet("activeCompanionId", finalId);
    } catch (e) { console.error("fetchRoster", e); set({ loading: false }); }
  },

  setActive: (id) => {
    if (id) lsSet("activeCompanionId", id);
    else lsRemove("activeCompanionId");
    set({ activeId: id });
  },

  create: async (name, backstory, personality) => {
    const c = await apiPost<Companion>("/companions", {
      name, avatar_path: null, backstory, personality,
      voice_config: null, memory_mode: "hybrid",
      model_name: "qwen3:14b", relationship_type: "friend",
    });
    set((s) => ({ roster: [...s.roster, c], activeId: c.id }));
    lsSet("activeCompanionId", c.id);
    return c;
  },

  remove: async (id) => {
    await apiDelete(`/companions/${id}`);
    set((s) => {
      const newActive = s.activeId === id ? (s.roster.find((c) => c.id !== id)?.id ?? null) : s.activeId;
      if (newActive) lsSet("activeCompanionId", newActive);
      else lsRemove("activeCompanionId");
      return {
        roster: s.roster.filter((c) => c.id !== id),
        activeId: newActive,
      };
    });
  },

  update: async (id, fields) => {
    const c = await apiPut<Companion>(`/companions/${id}`, fields);
    set((s) => ({ roster: s.roster.map((x) => (x.id === id ? c : x)) }));
    return c;
  },

  updateSoul: async (id, soul) => {
    await apiPut(`/companions/${id}/soul`, { soul });
  },
}));

// ── Chat store ────────────────────────────────────────────────────

interface ChatStoreState {
  messagesByCompanion: Record<string, Message[]>;
  sending: boolean;
  /** Per-companion flag: was the last assistant response regenerated or edited? */
  lastMeta: Record<string, { model: string; duration_ms: number; eval_count: number | null; ts: number } | null>;
  lastInteraction: { companion: string; text: string; ts: number } | null;
  fetchHistory: (companionId: string) => Promise<void>;
  send: (companionId: string, text: string) => Promise<void>;
  regenerate: (companionId: string, afterUserMessageId?: string) => Promise<void>;
  deleteMessage: (companionId: string, mid: string) => Promise<void>;
  editAndResend: (companionId: string, mid: string, newText: string) => Promise<void>;
  interact: (companionId: string, interaction: string) => Promise<void>;
  getLastUserText: (companionId: string) => string | null;
  rememberMessage: (companionId: string, msg: Message, category: string, importance: number, note?: string | null) => Promise<SemanticMemory>;
  rememberMessageAsDiary: (companionId: string, msg: Message, mood?: string | null) => Promise<DiaryEntry>;
  drawLastMoment: (companionId: string) => Promise<ImageGenResult | null>;
}

export const useChatStore = create<ChatStoreState>((set, get) => ({
  messagesByCompanion: {}, sending: false, lastMeta: {}, lastInteraction: null,

  fetchHistory: async (companionId) => {
    const msgs = await apiGet<Message[]>(`/chat/${companionId}/messages?limit=100`);
    set((s) => ({ messagesByCompanion: { ...s.messagesByCompanion, [companionId]: msgs } }));
  },

  send: async (companionId, text) => {
    if (!text.trim()) return;
    set({ sending: true });
    try {
      const result = await apiPost<ChatResult>("/chat/send", { companionId, text });
      set((s) => {
        const cur = s.messagesByCompanion[companionId] ?? [];
        return {
          messagesByCompanion: { ...s.messagesByCompanion, [companionId]: [...cur, result.user, result.assistant] },
          lastMeta: { ...s.lastMeta, [companionId]: {
            model: result.model,
            duration_ms: result.total_duration_ns ? Math.round(result.total_duration_ns / 1_000_000) : 0,
            eval_count: result.eval_count ?? null,
            ts: Date.now(),
          }},
        };
      });
      // Auto-consolidate in background
      apiPost(`/chat/consolidate`, { companionId, threshold: 20 })
        .then((r: unknown) => { if ((r as { count?: number }).count) useUIStore.getState().showToast(`🧠 New facts extracted`, "ok"); })
        .catch(() => {});
    } finally { set({ sending: false }); }
  },

  regenerate: async (companionId, afterUserMessageId) => {
    set({ sending: true });
    try {
      const result = await apiPost<ChatResult>("/chat/regenerate", {
        companionId,
        afterUserMessageId: afterUserMessageId ?? null,
      });
      // Re-fetch history to reflect the new state cleanly
      const msgs = await apiGet<Message[]>(`/chat/${companionId}/messages?limit=100`);
      set((s) => ({
        messagesByCompanion: { ...s.messagesByCompanion, [companionId]: msgs },
        lastMeta: { ...s.lastMeta, [companionId]: {
          model: result.model,
          duration_ms: result.total_duration_ns ? Math.round(result.total_duration_ns / 1_000_000) : 0,
          eval_count: result.eval_count ?? null,
          ts: Date.now(),
        }},
      }));
    } finally { set({ sending: false }); }
  },

  deleteMessage: async (companionId, mid) => {
    await apiDelete(`/chat/messages/${mid}`);
    set((s) => {
      const cur = s.messagesByCompanion[companionId] ?? [];
      return {
        messagesByCompanion: { ...s.messagesByCompanion, [companionId]: cur.filter((m) => m.id !== mid) },
      };
    });
  },

  editAndResend: async (companionId, mid, newText) => {
    set({ sending: true });
    try {
      const result = await apiPost<ChatResult>("/chat/edit-resend", {
        companionId, messageId: mid, newText,
      });
      const msgs = await apiGet<Message[]>(`/chat/${companionId}/messages?limit=100`);
      set((s) => ({
        messagesByCompanion: { ...s.messagesByCompanion, [companionId]: msgs },
        lastMeta: { ...s.lastMeta, [companionId]: {
          model: result.model,
          duration_ms: result.total_duration_ns ? Math.round(result.total_duration_ns / 1_000_000) : 0,
          eval_count: result.eval_count ?? null,
          ts: Date.now(),
        }},
      }));
    } finally { set({ sending: false }); }
  },

  interact: async (companionId, interaction) => {
    try {
      const result = await apiPost<{ narration: string; companion: string; interaction: string }>(
        "/chat/interact", { companionId, interaction }
      );
      set(() => ({ lastInteraction: { companion: result.companion, text: result.narration, ts: Date.now() } }));
      const msgs = await apiGet<Message[]>(`/chat/${companionId}/messages?limit=100`);
      set((s) => ({ messagesByCompanion: { ...s.messagesByCompanion, [companionId]: msgs } }));
    } catch (e) { console.error("interact failed", e); }
  },

  getLastUserText: (companionId) => {
    const msgs = get().messagesByCompanion[companionId] ?? [];
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "user") return msgs[i].content;
    }
    return null;
  },

  rememberMessage: async (companionId, msg, category, importance, note) => {
    const trimmed = msg.content.length > 280 ? `"${msg.content.slice(0, 280)}…"` : `"${msg.content}"`;
    const fact = note?.trim() ? `${note.trim()}: ${trimmed}` : `From our chat, you said: ${trimmed}`;
    const saved = await apiPost<SemanticMemory>("/memory", {
      companionId, factText: fact, category: category || null, importance: importance || 5,
    });
    await useMemoryStore.getState().fetchAll(companionId);
    return saved;
  },

  rememberMessageAsDiary: async (companionId, msg, mood) => {
    const entry = await apiPost<DiaryEntry>("/diary", {
      companionId, content: msg.content, moodTag: mood ?? null,
    });
    await useMemoryStore.getState().fetchAll(companionId);
    return entry;
  },

  drawLastMoment: async (companionId) => {
    const lastText = get().getLastUserText(companionId);
    if (!lastText) return null;
    const result = await apiPost<ImageGenResult>("/art/quick", { companionId, text: lastText });
    void useArtStore.getState().fetchHistory(companionId);
    return result;
  },
}));

// ── Memory store ─────────────────────────────────────────────────

interface MemoryStoreState {
  semantic: Record<string, SemanticMemory[]>;
  summaries: Record<string, SessionSummary[]>;
  diary: Record<string, DiaryEntry[]>;
  fetching: boolean;
  fetchAll: (companionId: string) => Promise<void>;
  addMemory: (companionId: string, fact: string, category?: string, importance?: number) => Promise<void>;
  updateMemory: (id: string, fact: string, category: string | null, importance: number) => Promise<void>;
  deleteMemory: (id: string) => Promise<void>;
  promoteToIdentity: (id: string) => Promise<void>;
  categoryCounts: Record<string, number>;
  loadCategoryCounts: (companionId: string) => Promise<void>;
  extractFacts: (companionId: string) => Promise<number>;
  saveSummary: (companionId: string, summary: string, emotionalTone?: string, relationshipState?: string) => Promise<void>;
  addDiary: (companionId: string, content: string, mood?: string) => Promise<void>;
  deleteDiary: (id: string) => Promise<void>;
}

export const useMemoryStore = create<MemoryStoreState>((set, get) => ({
  semantic: {}, summaries: {}, diary: {}, fetching: false, categoryCounts: {},

  fetchAll: async (companionId) => {
    set({ fetching: true });
    try {
      const [sem, sum, dia] = await Promise.all([
        apiGet<SemanticMemory[]>(`/memory/${companionId}`),
        apiGet<SessionSummary[]>(`/summaries/${companionId}?limit=10`),
        apiGet<DiaryEntry[]>(`/diary/${companionId}`),
      ]);
      set((s) => ({
        semantic: { ...s.semantic, [companionId]: sem },
        summaries: { ...s.summaries, [companionId]: sum },
        diary: { ...s.diary, [companionId]: dia },
        fetching: false,
      }));
    } catch (e) { console.error("fetchAll", e); set({ fetching: false }); }
  },

  addMemory: async (companionId, fact, category, importance) => {
    await apiPost("/memory", { companionId, factText: fact, category: category ?? null, importance: importance ?? null });
    await get().fetchAll(companionId);
  },

  updateMemory: async (id, fact, category, importance) => {
    await apiPost("/memory", { id, factText: fact, category, importance });
  },

  deleteMemory: async (id) => { await apiDelete(`/memory/${id}`); },

  promoteToIdentity: async (id) => {
    await apiPost(`/memory/${id}/promote`, {});
  },

  loadCategoryCounts: async (companionId) => {
    try {
      const counts = await apiGet<Record<string, number>>(`/memory/${companionId}/counts`);
      set(() => ({ categoryCounts: counts }));
    } catch (e) { console.error("loadCategoryCounts", e); }
  },

  extractFacts: async (companionId) => {
    const r = await apiPost<{ facts: ExtractedFact[] }>(`/memory/${companionId}/extract`, {});
    await get().fetchAll(companionId);
    return r.facts.length;
  },

  saveSummary: async (companionId, summary, emotionalTone, relationshipState) => {
    await apiPost("/summaries", { companionId, summary, emotionalTone: emotionalTone ?? null, relationshipState: relationshipState ?? null });
    await get().fetchAll(companionId);
  },

  addDiary: async (companionId, content, mood) => {
    await apiPost("/diary", { companionId, content, moodTag: mood ?? null });
    await get().fetchAll(companionId);
  },

  deleteDiary: async (id) => { await apiDelete(`/diary/${id}`); },
}));

// ── Art store ─────────────────────────────────────────────────────

interface ArtStoreState {
  history: Record<string, ArtEntry[]>;
  imageModels: OllamaModel[];
  generating: boolean;
  uploading: boolean;
  lastImage: { companion: string; url: string; prompt: string; kind?: "png" | "svg" } | null;
  fetchHistory: (companionId: string) => Promise<void>;
  fetchImageModels: () => Promise<void>;
  generate: (companionId: string, prompt: string, options?: {
    model?: string; size?: string; seed?: number; negativePrompt?: string; steps?: number;
  }) => Promise<ImageGenResult>;
  uploadArt: (companionId: string, file: File, prompt?: string) => Promise<{ id: string; file_path: string; prompt: string }>;
  deleteArt: (id: string) => Promise<void>;
}

export const useArtStore = create<ArtStoreState>((set, get) => ({
  history: {}, imageModels: [], generating: false, uploading: false, lastImage: null,

  fetchHistory: async (companionId) => {
    try {
      const history = await apiGet<ArtEntry[]>(`/art/${companionId}/history`);
      set((s) => ({ history: { ...s.history, [companionId]: history } }));
    } catch (e) { console.error("fetchHistory", e); }
  },

  fetchImageModels: async () => {
    try {
      const all = await apiGet<OllamaModel[]>("/ollama/image-models");
      const imageModels = all.filter((m) =>
        m.name.includes("flux") || m.name.includes("z-image") || m.name.includes("sdxl")
      );
      set({ imageModels });
    } catch (e) { console.error("fetchImageModels", e); }
  },

  generate: async (companionId, prompt, options = {}) => {
    set({ generating: true });
    try {
      const result = await apiPost<ImageGenResult>("/art/generate", {
        companionId, prompt,
        model: options.model ?? null, size: options.size ?? null,
        seed: options.seed ?? null, negativePrompt: options.negativePrompt ?? null,
        steps: options.steps ?? null,
      });
      // Detect SVG vs PNG from the result kind or by sniffing the base64
      // header. SVG starts with the bytes for "<svg", so when the bytes are
      // decoded, we can check.
      let url: string;
      let kind: "png" | "svg" | undefined = (result as { kind?: "png" | "svg" }).kind;
      if (!kind) {
        // Backward compat: sniff the base64 (PNG starts with iVBORw0KGgo)
        try {
          const head = atob(result.base64.slice(0, 16));
          kind = head.startsWith("<svg") || head.startsWith("<?xml") ? "svg" : "png";
        } catch { kind = "png"; }
      }
      const mime = kind === "svg" ? "image/svg+xml" : "image/png";
      url = `data:${mime};base64,${result.base64}`;
      set(() => ({ lastImage: { companion: companionId, url, prompt: result.id, kind } }));
      await get().fetchHistory(companionId);
      return result;
    } finally { set({ generating: false }); }
  },

  uploadArt: async (companionId, file, prompt = "") => {
    set({ uploading: true });
    try {
      const arrayBuf = await file.arrayBuffer();
      // chunk-safe base64
      const bytes = new Uint8Array(arrayBuf);
      let bin = "";
      const CHUNK = 0x8000;
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + CHUNK)));
      }
      const b64 = btoa(bin);
      const result = await apiPost<{ id: string; file_path: string; prompt: string }>(
        "/art/upload",
        {
          companionId,
          prompt: prompt || file.name || "Uploaded image",
          base64: b64,
          filename: file.name,
          mime: file.type || "image/png",
        }
      );
      // Set last image so the "remember this" panel shows
      const url = URL.createObjectURL(file);
      set(() => ({ lastImage: { companion: companionId, url, prompt: result.id } }));
      await get().fetchHistory(companionId);
      return result;
    } finally { set({ uploading: false }); }
  },

  deleteArt: async (id) => { await apiDelete(`/art/${id}`); },
}));

// ── Status / settings store ───────────────────────────────────────

export interface Heartbeat {
  ok: boolean;
  name: string;
  version: string;
  platform: string;
  machine: string;
  python_version: string;
  pid: number;
  uptime_s: number;
  started_at: string;
  now: string;
}

interface StatusState {
  appInfo: AppInfo | null; ollama: OllamaHealth | null; ollamaModels: OllamaModel[];
  heartbeat: Heartbeat | null;
  apiOnline: boolean;
  refreshAll: () => Promise<void>;
  /** Poll the heartbeat endpoint. Sets apiOnline=false if it fails. */
  checkHeartbeat: () => Promise<void>;
}

export const useStatusStore = create<StatusState>((set) => ({
  appInfo: null, ollama: null, ollamaModels: [],
  heartbeat: null,
  apiOnline: true,  // optimistic until proven otherwise

  refreshAll: async () => {
    try {
      const [info, ollama, models] = await Promise.all([
        apiGet<AppInfo>("/app-info"),
        apiGet<OllamaHealth>("/ollama/health"),
        apiGet<OllamaModel[]>("/ollama/models").catch(() => []),
      ]);
      set({ appInfo: info, ollama, ollamaModels: models, apiOnline: true });
    } catch (e) { console.error("refreshAll", e); }
  },

  checkHeartbeat: async () => {
    try {
      const h = await apiGet<Heartbeat>("/heartbeat");
      set({ heartbeat: h, apiOnline: true });
    } catch (e) {
      // Server is down. Mark offline but don't wipe the rest of the state —
      // the user might be looking at cached data while the API comes back.
      set({ apiOnline: false });
    }
  },
}));

// ── UI store ─────────────────────────────────────────────────────

interface UIState {
  activeTab: "chat" | "memory" | "art" | "settings" | "models" | "cards" | "inner";
  setTab: (t: UIState["activeTab"]) => void;
  showWizard: boolean; openWizard: () => void; closeWizard: () => void;
  showBackup: boolean; openBackup: () => void; closeBackup: () => void;
  editingId: string | null; openEditor: (id: string) => void; closeEditor: () => void;
  toast: { id: number; text: string; kind: "ok" | "err" } | null;
  showToast: (text: string, kind?: "ok" | "err") => void;
}

export const useUIStore = create<UIState>((set) => ({
  // Read the persisted tab on init; fall back to "chat". Validate against
  // known tab ids so a stale "foo" doesn't crash the tabs.
  activeTab: (() => {
    const valid = ["chat", "memory", "art", "settings", "models", "cards", "inner"] as const;
    const saved = lsGet("activeTab");
    return saved && (valid as readonly string[]).includes(saved) ? (saved as UIState["activeTab"]) : "chat";
  })(),
  setTab: (activeTab) => { lsSet("activeTab", activeTab); set({ activeTab }); },
  showWizard: false,
  openWizard: () => set({ showWizard: true }),
  closeWizard: () => set({ showWizard: false }),
  showBackup: false,
  openBackup: () => set({ showBackup: true }),
  closeBackup: () => set({ showBackup: false }),
  editingId: null,
  openEditor: (id) => set({ editingId: id }),
  closeEditor: () => set({ editingId: null }),
  toast: null,
  showToast: (text, kind = "ok") => {
    const id = Date.now();
    set({ toast: { id, text, kind } });
    setTimeout(() => {
      const cur = useUIStore.getState().toast;
      if (cur && cur.id === id) set({ toast: null });
    }, 4500);
  },
}));
