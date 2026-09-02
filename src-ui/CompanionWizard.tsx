import { useState } from "react";
import {
  type EnneagramPicks,
  EnneagramStep,
} from "./EnneagramStep";
import { type AvatarResult, type ChatResult, useCompanionStore, useUIStore } from "./stores";

const API = "/api";
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
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

interface WizardProps {
  onClose: () => void;
  onCreated: (companionId: string) => void;
}

// v0.15 — Enneagram-driven wizard. Big Five / Ocean was replaced because
// the Enneagram is a richer framework for personality and gives the LLM
// something concrete to draw from (type, wing, instinct, health).
const STEPS = [
  "Identity",
  "Archetype",
  "Personality",
  "Backstory",
  "Voice",
  "Avatar",
  "Review",
] as const;
type Step = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export function CompanionWizard({ onClose, onCreated }: WizardProps) {
  const { fetchRoster, setActive } = useCompanionStore();
  const setTab = useUIStore((s) => s.setTab);
  const [step, setStep] = useState<Step>(0);

  // Step 0: Identity
  const [name, setName] = useState("");
  const [pronouns, setPronouns] = useState("she");
  const [ageBracket, setAgeBracket] = useState("adult");
  const [hook, setHook] = useState("");

  // Step 1: Archetype (kept as flavor — defines the relationship vibe)
  const [archetype, setArchetype] = useState("mentor");
  const [relationshipType, setRelationshipType] = useState("friend");

  // Step 2: Enneagram — quiz or manual pick, then wing/instinct/health
  const [picks, setPicks] = useState<EnneagramPicks>({
    type: null,
    wing: null,
    instinct: "sp",
    health: "average",
  });
  const [soul, setSoul] = useState<string | null>(null);
  const [generatingSoul, setGeneratingSoul] = useState(false);

  // Step 3: Backstory (freeform notes) — appended to the soul
  const [freeformNotes, setFreeformNotes] = useState("");

  // Step 4: Voice
  const [voiceId, setVoiceId] = useState("af_heart");
  const [voiceDescription, setVoiceDescription] = useState("warm, even-tempered");
  const voiceSpeed = 1.0;
  const voicePitch = 0.0;

  // Step 5: Avatar
  const [generatingAvatar, setGeneratingAvatar] = useState(false);
  const [avatar, setAvatar] = useState<AvatarResult | null>(null);

  // Step 6: Save
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preview chat (step 6)
  const [previewSending, setPreviewSending] = useState(false);
  const [previewText, setPreviewText] = useState<string | null>(null);

  function next() {
    if (step < 6) setStep((step + 1) as Step);
  }
  function back() {
    if (step > 0) setStep((step - 1) as Step);
  }

  async function generateSoulFromEnneagram() {
    if (picks.type === null) {
      setError("Pick an Enneagram type first.");
      return;
    }
    setGeneratingSoul(true);
    setError(null);
    try {
      const r = await apiPost<{ soul: string }>("/enneagram/build-soul", {
        type: picks.type,
        wing: picks.wing,
        instinct: picks.instinct,
        health: picks.health,
        name: name.trim() || null,
      });
      setSoul(r.soul);
    } catch (e) {
      setError(`Soul generation failed: ${e}`);
    } finally {
      setGeneratingSoul(false);
    }
  }

  async function generateAvatar() {
    if (!soul) {
      setError("Generate the soul first.");
      return;
    }
    setGeneratingAvatar(true);
    setError(null);
    try {
      const a = await apiPost<AvatarResult>("/art/avatar", {
        companionName: name.trim(),
        archetype,
        soul,
        imageModel: null,
        size: "1024x1024",
      });
      setAvatar(a);
    } catch (e) {
      setError(`Avatar generation failed: ${e}`);
    } finally {
      setGeneratingAvatar(false);
    }
  }

  async function previewChat() {
    if (!soul) {
      setError("Generate the soul first.");
      return;
    }
    setPreviewSending(true);
    setPreviewText(null);
    setError(null);
    try {
      const previewName = `${name.trim()} (preview)`;
      const voiceConfig = JSON.stringify({
        engine: "kokoro",
        voice_id: voiceId,
        speed: voiceSpeed,
        pitch: voicePitch,
        description: voiceDescription,
      });
      const c = await apiPost<{ id: string }>("/companions/full", {
        name: previewName,
        soul,
        archetype,
        relationshipType,
        memoryMode: "hybrid",
        voiceConfig,
        avatarPath: null,
        enneagramType: picks.type,
        enneagramWing: picks.wing,
        enneagramInstinct: picks.instinct,
        enneagramHealth: picks.health,
      });
      await fetchRoster();
      try {
        const result = await apiPost<ChatResult>("/chat/send", {
          companionId: c.id,
          text: "Hi! Tell me about yourself in two sentences.",
        });
        setPreviewText(result.assistant.content);
      } finally {
        try {
          await apiDelete(`/companions/${c.id}`);
          await fetchRoster();
        } catch {
          /* ignore */
        }
      }
    } catch (e) {
      setError(`Preview failed: ${e}`);
    } finally {
      setPreviewSending(false);
    }
  }

  async function saveAll() {
    if (!soul) {
      setError("Generate the soul first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // Append freeform notes to the soul if the user added any
      let finalSoul = soul;
      if (freeformNotes.trim()) {
        finalSoul = soul + "\n\n## Custom Notes\n\n" + freeformNotes.trim() + "\n";
      }
      const voiceConfig = JSON.stringify({
        engine: "kokoro",
        voice_id: voiceId,
        speed: voiceSpeed,
        pitch: voicePitch,
        description: voiceDescription,
      });
      const c = await apiPost<{ id: string }>("/companions/full", {
        name: name.trim(),
        soul: finalSoul,
        archetype,
        relationshipType,
        memoryMode: "hybrid",
        voiceConfig,
        avatarPath: avatar?.file_path ?? null,
        enneagramType: picks.type,
        enneagramWing: picks.wing,
        enneagramInstinct: picks.instinct,
        enneagramHealth: picks.health,
      });
      await fetchRoster();
      setActive(c.id);
      setTab("chat");
      onCreated(c.id);
    } catch (e) {
      setError(`Save failed: ${e}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wizard" onClick={(e) => e.stopPropagation()}>
        <header className="wizard-header">
          <h2>New companion</h2>
          <button className="close" onClick={onClose}>×</button>
        </header>

        <div className="wizard-steps">
          {STEPS.map((label, i) => (
            <button
              key={label}
              className={`wizard-step ${i === step ? "active" : ""} ${i < step ? "done" : ""}`}
              onClick={() => setStep(i as Step)}
              disabled={i > step}
            >
              <span className="num">{i + 1}</span>
              <span className="lbl">{label}</span>
            </button>
          ))}
        </div>

        <div className="wizard-body">
          {step === 0 && (
            <div className="step">
              <h3>Identity</h3>
              <p className="hint">Who is this person?</p>
              <label>
                Name
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Mira"
                  maxLength={40}
                />
              </label>
              <label>
                Pronouns
                <select value={pronouns} onChange={(e) => setPronouns(e.target.value)}>
                  <option value="she">she / her</option>
                  <option value="he">he / him</option>
                  <option value="they">they / them</option>
                  <option value="it">it / its</option>
                  <option value="any">any pronouns</option>
                </select>
              </label>
              <label>
                Apparent age
                <select value={ageBracket} onChange={(e) => setAgeBracket(e.target.value)}>
                  <option value="young">Young (child / teen)</option>
                  <option value="adult">Adult</option>
                  <option value="middle">Middle-aged</option>
                  <option value="elder">Elder</option>
                  <option value="timeless">Timeless / ageless</option>
                </select>
              </label>
              <label>
                Hook (one line — the thing that makes them memorable)
                <input
                  value={hook}
                  onChange={(e) => setHook(e.target.value)}
                  placeholder="e.g. the barista who remembers your name"
                />
              </label>
            </div>
          )}

          {step === 1 && (
            <div className="step">
              <h3>Archetype</h3>
              <p className="hint">What role do they play in your life?</p>
              <div className="grid-2">
                {[
                  { id: "mentor", label: "Mentor — wise, guiding" },
                  { id: "nurturer", label: "Nurturer — warm, caring" },
                  { id: "rebel", label: "Rebel — bold, free" },
                  { id: "creator", label: "Creator — imaginative" },
                  { id: "explorer", label: "Explorer — curious" },
                  { id: "innocent", label: "Innocent — pure, hopeful" },
                  { id: "sage", label: "Sage — thoughtful" },
                  { id: "jester", label: "Jester — playful" },
                  { id: "lover", label: "Lover — passionate" },
                  { id: "ruler", label: "Ruler — authoritative" },
                ].map((a) => (
                  <button
                    key={a.id}
                    className={`archetype-card ${archetype === a.id ? "active" : ""}`}
                    onClick={() => {
                      setArchetype(a.id);
                      setRelationshipType(
                        a.id === "rebel" ? "friend" :
                        a.id === "ruler" ? "mentor" :
                        a.id === "nurturer" ? "family" :
                        a.id === "creator" ? "friend" :
                        a.id === "explorer" ? "friend" :
                        a.id === "innocent" ? "friend" :
                        a.id === "jester" ? "friend" :
                        a.id === "lover" ? "partner" :
                        a.id === "sage" ? "mentor" :
                        "friend"
                      );
                    }}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 2 && (
            <EnneagramStep
              picks={picks}
              setPicks={setPicks}
              soulPreview={soul}
              onGenerateSoul={generateSoulFromEnneagram}
              generating={generatingSoul}
            />
          )}

          {step === 3 && (
            <div className="step">
              <h3>Backstory (optional)</h3>
              <p className="hint">
                Add any extra notes — loves, scars, secrets, mannerisms, hobbies.
                These will be appended to the soul.md as a "Custom Notes" section.
              </p>
              <textarea
                value={freeformNotes}
                onChange={(e) => setFreeformNotes(e.target.value)}
                rows={6}
                placeholder="Optional. e.g. 'Has a small scar on their left hand from a childhood fall. Always carries an old paperback. Secretly loves bad pop music.'"
                style={{ width: "100%" }}
              />
              {soul && (
                <details style={{ marginTop: 12 }}>
                  <summary>Preview generated soul.md</summary>
                  <pre style={{ maxHeight: 240, overflow: "auto", fontSize: 12 }}>
                    {soul}
                  </pre>
                </details>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="step">
              <h3>Voice</h3>
              <p className="hint">Pick a voice pack for voice mode.</p>
              <div className="voice-grid">
                {[
                  { id: "af_heart", name: "Heart", gender: "F", language: "en-US" },
                  { id: "af_bella", name: "Bella", gender: "F", language: "en-US" },
                  { id: "af_nova", name: "Nova", gender: "F", language: "en-US" },
                  { id: "am_michael", name: "Michael", gender: "M", language: "en-US" },
                  { id: "am_fenrir", name: "Fenrir", gender: "M", language: "en-US" },
                  { id: "bf_emma", name: "Emma", gender: "F", language: "en-GB" },
                  { id: "bm_george", name: "George", gender: "M", language: "en-GB" },
                ].map((v) => (
                  <button
                    key={v.id}
                    className={`voice-card ${voiceId === v.id ? "active" : ""}`}
                    onClick={() => setVoiceId(v.id)}
                  >
                    <div className="voice-id">{v.id}</div>
                    <div className="voice-name">{v.name}</div>
                    <div className="voice-meta">{v.language} · {v.gender}</div>
                  </button>
                ))}
              </div>
              <label style={{ marginTop: 16 }}>
                Voice description (for the prompt)
                <input
                  value={voiceDescription}
                  onChange={(e) => setVoiceDescription(e.target.value)}
                  placeholder="e.g. low, slow, with a slight rasp"
                />
              </label>
            </div>
          )}

          {step === 5 && (
            <div className="step">
              <h3>Avatar</h3>
              <p className="hint">
                Generate a portrait from their soul. The image gen uses Ollama
                with an SVG-fallback (so it always works, no extra deps).
              </p>
              <button
                className="primary"
                onClick={generateAvatar}
                disabled={generatingAvatar || !soul}
                style={{ marginTop: 8 }}
              >
                {generatingAvatar
                  ? <><span className="spinner" /> Generating portrait…</>
                  : <>🎨 Generate avatar</>}
              </button>
              {avatar && (
                <div className="avatar-preview">
                  <img
                    src={
                      avatar.kind === "svg"
                        ? `data:image/svg+xml;base64,${avatar.base64}`
                        : `data:image/png;base64,${avatar.base64}`
                    }
                    alt="avatar"
                  />
                  <p className="hint">
                    {avatar.width}×{avatar.height} · {avatar.model} ·{" "}
                    {Math.round(avatar.duration_ms / 100) / 10}s
                  </p>
                </div>
              )}
              <p className="hint" style={{ marginTop: 12, fontSize: 12 }}>
                Or skip and set an avatar later.
              </p>
            </div>
          )}

          {step === 6 && (
            <div className="step review">
              <h3>Review & save</h3>
              <div className="review-card">
                <h2>{name || "(no name)"}</h2>
                {avatar && (
                  <img
                    src={
                      avatar.kind === "svg"
                        ? `data:image/svg+xml;base64,${avatar.base64}`
                        : `data:image/png;base64,${avatar.base64}`
                    }
                    alt="avatar"
                  />
                )}
                <div className="review-meta">
                  <span className="tag">{pronouns}</span>
                  <span className="tag">{ageBracket}</span>
                  <span className="tag">{archetype}</span>
                  {picks.type !== null && (
                    <span className="tag enneagram-tag">
                      Enneagram {picks.type}
                      {picks.wing ? `w${picks.wing}` : ""}
                      {" · "}
                      {picks.instinct} · {picks.health}
                    </span>
                  )}
                </div>
                {soul && (
                  <details className="soul-expand">
                    <summary>soul.md ({soul.length} chars)</summary>
                    <pre>{soul}</pre>
                  </details>
                )}
              </div>

              {/* Preview chat — try a hello before committing. */}
              <div
                className="preview-chat"
                style={{
                  marginTop: 16,
                  padding: 12,
                  background: "var(--bg-elev)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: previewText ? 8 : 0,
                  }}
                >
                  <span style={{ fontSize: 12, color: "var(--text-muted)", flex: 1 }}>
                    Try a hello before you commit:
                  </span>
                  <button
                    className="primary"
                    onClick={() => void previewChat()}
                    disabled={previewSending || !soul}
                    style={{ fontSize: 12 }}
                  >
                    {previewSending ? (
                      <><span className="spinner" /> Listening…</>
                    ) : (
                      <>💬 preview chat</>
                    )}
                  </button>
                </div>
                {previewText && (
                  <div
                    style={{
                      fontStyle: "italic",
                      padding: "8px 0",
                      borderTop: "1px solid var(--border)",
                      fontSize: 13,
                    }}
                  >
                    <strong style={{ fontStyle: "normal" }}>{name}:</strong>{" "}
                    {previewText}
                  </div>
                )}
              </div>
            </div>
          )}

          {error && <p className="wizard-error">✗ {error}</p>}
        </div>

        <footer className="wizard-footer">
          <button onClick={back} disabled={step === 0}>
            ← Back
          </button>
          <span style={{ flex: 1 }} />
          {step < 6 ? (
            <button
              className="primary"
              onClick={next}
              disabled={
                (step === 0 && !name.trim()) ||
                (step === 2 && picks.type === null) ||
                (step === 2 && !soul)
              }
            >
              Next →
            </button>
          ) : (
            <button className="primary" onClick={saveAll} disabled={saving || !soul}>
              {saving ? "Saving…" : "✦ Create companion"}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
