/**
 * Enneagram wizard step — pick a personality framework for the companion.
 *
 * Two paths:
 *   1) Take the 9-question quiz (pairwise A/B comparisons)
 *   2) Pick a type manually from the 9-type grid
 *
 * After picking, the user selects wing, instinct, and health level —
 * these add nuance to the type. Then "Generate soul" previews the
 * generated soul.md based on the Enneagram metadata.
 */
import { useEffect, useState } from "react";

export type EnneagramType = {
  name: string;
  one_liner: string;
  core_fear: string;
  core_desire: string;
  triad: string;
  center: string;
  integration: number;
  disintegration: number;
  communication: string;
  values: string[];
  strengths: string[];
  blind_spots: string[];
  stress_behaviors: string;
  growth_behaviors: string;
  voice_examples: string[];
  wings: Record<number, string>;
  in_a_sentence: string;
};

export type EnneagramQuizQuestion = {
  type_a: number;
  type_b: number;
  a: string;
  b: string;
};

export type EnneagramPicks = {
  type: number | null;
  wing: number | null;
  instinct: "sp" | "so" | "sx";
  health: "healthy" | "average" | "unhealthy";
};

type QuizState = "intro" | "taking" | "results" | "manual";

const TRIAD_COLOR: Record<string, string> = {
  gut: "#e6a23c",
  heart: "#e85a71",
  head: "#5c8aff",
};

const INSTINCT_LABEL: Record<string, string> = {
  sp: "Self-Preservation (sp)",
  so: "Social (so)",
  sx: "Sexual / One-to-One (sx)",
};

const HEALTH_LABEL: Record<string, string> = {
  healthy: "Healthy — wise, generous, integrated",
  average: "Average — typical, day-to-day",
  unhealthy: "Unhealthy — under stress, patterns hardened",
};

export function EnneagramStep({
  picks,
  setPicks,
  soulPreview,
  onGenerateSoul,
  generating,
}: {
  picks: EnneagramPicks;
  setPicks: (p: EnneagramPicks) => void;
  soulPreview: string | null;
  onGenerateSoul: () => void;
  generating: boolean;
}) {
  const [quizState, setQuizState] = useState<QuizState>("intro");
  const [types, setTypes] = useState<Record<number, EnneagramType> | null>(null);
  const [questions, setQuestions] = useState<EnneagramQuizQuestion[] | null>(null);
  const [answers, setAnswers] = useState<Record<number, "A" | "B">>({});
  const [quizResult, setQuizResult] = useState<{
    primary_type: number;
    wing: number | null;
    confidence: string;
    scores: Record<number, number>;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [tRes, qRes] = await Promise.all([
          fetch("/api/enneagram/types").then((r) => r.json()),
          fetch("/api/enneagram/quiz").then((r) => r.json()),
        ]);
        if (!cancelled) {
          setTypes(tRes);
          setQuestions(qRes);
        }
      } catch (e) {
        if (!cancelled) setError(`Failed to load Enneagram data: ${e}`);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!types || !questions) {
    return (
      <div className="step">
        <h3>Personality (Enneagram)</h3>
        <p className="hint">Loading…</p>
        {error && <p className="hint" style={{ color: "var(--err)" }}>{error}</p>}
      </div>
    );
  }

  // ── Quiz flow ───────────────────────────────────────────────
  if (quizState === "taking") {
    return (
      <div className="step">
        <h3>Personality (Enneagram)</h3>
        <p className="hint">
          For each pair, pick the statement that fits the person better. There's
          no right answer — go with your gut.
        </p>
        <div className="quiz">
          {questions.map((q, i) => {
            const chosen = answers[i];
            return (
              <div key={i} className="quiz-item enneagram-pair">
                <div className="pair-row">
                  <button
                    className={`pair-btn ${chosen === "A" ? "active" : ""}`}
                    onClick={() => setAnswers((prev) => ({ ...prev, [i]: "A" }))}
                  >
                    <span className="pair-letter">A</span>
                    <span className="pair-text">{q.a}</span>
                  </button>
                  <span className="pair-or">or</span>
                  <button
                    className={`pair-btn ${chosen === "B" ? "active" : ""}`}
                    onClick={() => setAnswers((prev) => ({ ...prev, [i]: "B" }))}
                  >
                    <span className="pair-letter">B</span>
                    <span className="pair-text">{q.b}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        {Object.keys(answers).length < questions.length && (
          <p className="hint" style={{ marginTop: 12, color: "var(--warn)" }}>
            {questions.length - Object.keys(answers).length} unanswered
          </p>
        )}
        <div className="step-actions">
          <button onClick={() => { setQuizState("intro"); setAnswers({}); setQuizResult(null); }}>
            ← Back
          </button>
          <button
            className="primary"
            disabled={Object.keys(answers).length === 0}
            onClick={async () => {
              try {
                const arr = questions.map((_, i) => answers[i] ?? null);
                const result = await fetch("/api/enneagram/quiz/score", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ answers: arr }),
                }).then((r) => r.json());
                setQuizResult(result);
                setQuizState("results");
              } catch (e) {
                setError(`Quiz scoring failed: ${e}`);
              }
            }}
          >
            Score quiz →
          </button>
        </div>
      </div>
    );
  }

  if (quizState === "results" && quizResult) {
    const primaryType = types[quizResult.primary_type];
    const wingType = quizResult.wing ? types[quizResult.wing] : null;
    return (
      <div className="step">
        <h3>Your result</h3>
        <div className="enneagram-result" style={{ borderLeft: `4px solid ${TRIAD_COLOR[primaryType.triad]}` }}>
          <div className="result-type">
            <div className="result-num">Type {quizResult.primary_type}</div>
            <div className="result-name">{primaryType.name}</div>
            {wingType && (
              <div className="result-wing">
                Wing {quizResult.wing} — {wingType.name}
              </div>
            )}
            <div className="result-confidence">
              Confidence: {quizResult.confidence}
            </div>
          </div>
          <p className="result-one-liner">{primaryType.one_liner}</p>
          <p className="result-sentence">{primaryType.in_a_sentence}</p>
          <details className="result-details">
            <summary>See full type profile</summary>
            <div className="result-detail-body">
              <p><strong>Core fear:</strong> {primaryType.core_fear}</p>
              <p><strong>Core desire:</strong> {primaryType.core_desire}</p>
              <p><strong>Communication:</strong> {primaryType.communication}</p>
              <p><strong>Values:</strong> {primaryType.values.join(", ")}</p>
              <p><strong>Strengths:</strong> {primaryType.strengths.join(", ")}</p>
              <p><strong>Under stress:</strong> {primaryType.stress_behaviors}</p>
              <p><strong>In growth:</strong> {primaryType.growth_behaviors}</p>
            </div>
          </details>
        </div>

        <div className="refine">
          <h4>Refine</h4>
          <p className="hint">Add nuance — wings shift the type, instinct is where attention goes, health is how much of the type is showing.</p>
          <div className="refine-grid">
            <label>
              Wing
              <select
                value={picks.wing ?? ""}
                onChange={(e) =>
                  setPicks({
                    ...picks,
                    type: quizResult.primary_type,
                    wing: e.target.value ? Number(e.target.value) : null,
                  })
                }
              >
                <option value="">None</option>
                {Object.entries(primaryType.wings).map(([wn, wdesc]) => (
                  <option key={wn} value={wn}>
                    {wn} — {wdesc.split(" — ")[0]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Instinct
              <select
                value={picks.instinct}
                onChange={(e) =>
                  setPicks({ ...picks, instinct: e.target.value as "sp" | "so" | "sx" })
                }
              >
                {Object.entries(INSTINCT_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Health
              <select
                value={picks.health}
                onChange={(e) =>
                  setPicks({ ...picks, health: e.target.value as "healthy" | "average" | "unhealthy" })
                }
              >
                {Object.entries(HEALTH_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="step-actions">
          <button onClick={() => { setQuizState("intro"); setAnswers({}); setQuizResult(null); }}>
            ← Start over
          </button>
          <button
            className="primary"
            onClick={() => {
              setPicks({ ...picks, type: quizResult.primary_type });
              onGenerateSoul();
            }}
            disabled={generating}
          >
            {generating ? <><span className="spinner" /> Generating soul.md…</> : "✦ Generate soul preview"}
          </button>
        </div>
      </div>
    );
  }

  // ── Manual pick ─────────────────────────────────────────────
  if (quizState === "manual") {
    return (
      <div className="step">
        <h3>Personality (Enneagram) — pick a type</h3>
        <p className="hint">9 types. Pick the one that fits the person best.</p>
        <div className="type-grid">
          {Object.entries(types).map(([n, t]) => (
            <button
              key={n}
              className={`type-card ${picks.type === Number(n) ? "active" : ""}`}
              onClick={() => {
                const next = { ...picks, type: Number(n), wing: null };
                setPicks(next);
              }}
              style={{ borderLeft: `4px solid ${TRIAD_COLOR[t.triad]}` }}
            >
              <div className="type-card-num">Type {n}</div>
              <div className="type-card-name">{t.name}</div>
              <div className="type-card-one-liner">{t.one_liner}</div>
            </button>
          ))}
        </div>
        {picks.type !== null && (
          <div className="refine" style={{ marginTop: 16 }}>
            <h4>Refine</h4>
            <div className="refine-grid">
              <label>
                Wing
                <select
                  value={picks.wing ?? ""}
                  onChange={(e) =>
                    setPicks({ ...picks, wing: e.target.value ? Number(e.target.value) : null })
                  }
                >
                  <option value="">None</option>
                  {Object.entries(types[picks.type].wings).map(([wn, wdesc]) => (
                    <option key={wn} value={wn}>
                      {wn} — {wdesc.split(" — ")[0]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Instinct
                <select
                  value={picks.instinct}
                  onChange={(e) =>
                    setPicks({ ...picks, instinct: e.target.value as "sp" | "so" | "sx" })
                  }
                >
                  {Object.entries(INSTINCT_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                Health
                <select
                  value={picks.health}
                  onChange={(e) =>
                    setPicks({ ...picks, health: e.target.value as "healthy" | "average" | "unhealthy" })
                  }
                >
                  {Object.entries(HEALTH_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        )}
        <div className="step-actions">
          <button onClick={() => setQuizState("intro")}>← Back</button>
          <button
            className="primary"
            disabled={picks.type === null || generating}
            onClick={onGenerateSoul}
          >
            {generating ? <><span className="spinner" /> Generating soul.md…</> : "✦ Generate soul preview"}
          </button>
        </div>
      </div>
    );
  }

  // ── Intro: choose quiz or manual ────────────────────────────
  return (
    <div className="step">
      <h3>Personality (Enneagram)</h3>
      <p className="hint">
        The Enneagram is a 9-type personality framework — each type has a core
        fear, a core desire, and a distinctive way of moving through the world.
        Pick the type that best fits this person, or take the 9-question quiz.
      </p>
      <div className="quiz-paths">
        <button
          className="path-card"
          onClick={() => setQuizState("taking")}
        >
          <div className="path-icon">?</div>
          <div className="path-name">Take the 9-question quiz</div>
          <div className="path-desc">
            Pick A or B for each pair. ~2 minutes. Best if you don't know the type.
          </div>
        </button>
        <button
          className="path-card"
          onClick={() => setQuizState("manual")}
        >
          <div className="path-icon">⌘</div>
          <div className="path-name">Pick manually</div>
          <div className="path-desc">
            Browse all 9 types. Best if you already know the type.
          </div>
        </button>
      </div>

      {soulPreview && (
        <div className="soul-preview-inline" style={{ marginTop: 16 }}>
          <details>
            <summary>Preview soul.md (click to view)</summary>
            <pre style={{ maxHeight: 240, overflow: "auto" }}>{soulPreview}</pre>
          </details>
          <button
            className="primary"
            onClick={onGenerateSoul}
            disabled={generating || picks.type === null}
            style={{ marginTop: 8 }}
          >
            {generating ? <><span className="spinner" /> Regenerating…</> : "Regenerate"}
          </button>
        </div>
      )}
    </div>
  );
}
