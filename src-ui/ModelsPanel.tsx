import { useEffect, useState, useRef, useCallback } from "react";
import { type ModelInfo } from "./stores";

const API = "/api";

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "chat", label: "Chat" },
  { id: "embedding", label: "Memory" },
  { id: "image", label: "Art" },
] as const;

type StepState = "done" | "active" | "pending" | "error";

interface SystemStatus {
  ollama_installed: boolean;
  ollama_running: boolean;
  ollama_version: string | null;
  ollama_path: string | null;
  ollama_app_path: string | null;
  platform: "darwin" | "windows" | "linux";
  models_total: number;
  models_installed: string[];
  has_chat_model: boolean;
  has_embed_model: boolean;
  has_image_model: boolean;
  setup_complete: boolean;
}

interface Recommendation {
  name: string;
  label: string;
  size: string;
  ram_needed: string;
  why: string;
  fallback_name?: string;
  fallback_label?: string;
  fallback_size?: string;
  fallback_why?: string;
}

interface PullJob {
  id: string;
  model: string;
  status: "starting" | "pulling" | "done" | "error" | "cancelled";
  progress_pct: number;
  bytes_done: number;
  bytes_total: number;
  layers: Array<{ digest: string; pct: number; status: string }>;
  error: string | null;
  log_tail: string[];
  started_at: number;
  finished_at: number | null;
  elapsed_s: number;
}

const PLATFORM_LABEL: Record<string, string> = {
  darwin: "macOS",
  windows: "Windows",
  linux: "Linux",
};
const DOWNLOAD_URL: Record<string, string> = {
  darwin: "https://ollama.com/download/mac",
  windows: "https://ollama.com/download/windows",
  linux: "https://ollama.com/download/linux",
};

function StatusDot({ ok, label }: { ok: boolean | null; label: string }) {
  const state = ok === null ? "unknown" : ok ? "ok" : "bad";
  return (
    <span className="setup-status">
      <span className={`setup-dot ${state}`} />
      <span>{label}</span>
    </span>
  );
}

function StepRow({
  state,
  number,
  title,
  children,
}: {
  state: StepState;
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  const icon = state === "done" ? "✓" : state === "error" ? "!" : number;
  return (
    <div className={`setup-step state-${state}`}>
      <div className="setup-step-marker">
        <span className="setup-step-icon">{icon}</span>
      </div>
      <div className="setup-step-body">
        <div className="setup-step-title">{title}</div>
        <div className="setup-step-detail">{children}</div>
      </div>
    </div>
  );
}

function ProgressBar({ pct, status }: { pct: number; status: string }) {
  const capped = Math.max(0, Math.min(100, pct));
  return (
    <div className="pull-progress">
      <div className="pull-progress-track">
        <div
          className={`pull-progress-fill ${status === "error" ? "error" : status === "done" ? "done" : ""}`}
          style={{ width: `${capped}%` }}
        />
      </div>
      <span className="pull-progress-label">{Math.round(capped)}%</span>
    </div>
  );
}

export function ModelsPanel() {
  // Catalog (existing)
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "chat" | "embedding" | "image">("all");

  // Onboarding (new)
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [reco, setReco] = useState<{ chat: Recommendation; embedding: Recommendation } | null>(null);
  const [activeJobs, setActiveJobs] = useState<Record<string, PullJob>>({});
  const [recheckNonce, setRecheckNonce] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/system/status`);
      if (r.ok) setStatus(await r.json());
    } catch (e) { console.error("status", e); }
    finally { setStatusLoading(false); }
  }, []);

  const fetchReco = useCallback(async () => {
    try {
      const r = await fetch(`${API}/system/recommend`);
      if (r.ok) setReco(await r.json());
    } catch (e) { console.error("reco", e); }
  }, []);

  const fetchCatalog = useCallback(async () => {
    try {
      const r = await fetch(`${API}/models/catalog`);
      if (r.ok) setModels(await r.json());
    } catch (e) { console.error("catalog", e); }
    finally { setCatalogLoading(false); }
  }, []);

  const fetchActiveJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/models/pull-jobs`);
      if (r.ok) {
        const jobs: PullJob[] = await r.json();
        // Show only running/starting jobs in the active list
        const active: Record<string, PullJob> = {};
        for (const j of jobs) {
          if (j.status === "pulling" || j.status === "starting") {
            active[j.id] = j;
          }
        }
        setActiveJobs(active);
      }
    } catch (e) { console.error("jobs", e); }
  }, []);

  // Initial load
  useEffect(() => { fetchStatus(); fetchReco(); fetchCatalog(); },
    [fetchStatus, fetchReco, fetchCatalog, recheckNonce]);

  // Poll active jobs every 1.5s while any are running
  useEffect(() => {
    const hasRunning = Object.values(activeJobs).some(
      (j) => j.status === "pulling" || j.status === "starting"
    );
    if (hasRunning && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        await fetchActiveJobs();
        await fetchStatus();
        await fetchCatalog();
      }, 1500);
    }
    if (!hasRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [activeJobs, fetchActiveJobs, fetchStatus, fetchCatalog]);

  // Re-poll active jobs once on mount to recover UI state
  useEffect(() => { fetchActiveJobs(); }, [fetchActiveJobs]);

  const filtered = filter === "all" ? models : models.filter((m) => m.category === filter);

  function copy(cmd: string) {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(cmd);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  async function startInstall(model: string): Promise<void> {
    try {
      const r = await fetch(`${API}/models/pull`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
      });
      const data = await r.json();
      if (data.already_installed) {
        // Refresh status immediately
        setRecheckNonce((n) => n + 1);
        return;
      }
      if (data.job_id) {
        // Optimistically add the job
        setActiveJobs((prev) => ({
          ...prev,
          [data.job_id]: {
            id: data.job_id, model: data.model,
            status: "starting", progress_pct: 0,
            bytes_done: 0, bytes_total: 0,
            layers: [], error: null, log_tail: [],
            started_at: Date.now() / 1000, finished_at: null, elapsed_s: 0,
          },
        }));
        // Start polling right away
        setTimeout(fetchActiveJobs, 500);
      }
    } catch (e) {
      console.error("start install", e);
    }
  }

  async function cancelJob(jobId: string) {
    await fetch(`${API}/models/pull/${jobId}`, { method: "DELETE" });
    fetchActiveJobs();
  }

  async function launchOllama() {
    await fetch(`${API}/system/launch-ollama`, { method: "POST" });
    // Wait a moment, then re-check
    setTimeout(() => setRecheckNonce((n) => n + 1), 2000);
  }

  // ── Onboarding step states ──
  const step1State: StepState = !status ? "pending"
    : status.ollama_installed ? "done" : "active";
  const step2State: StepState = !status ? "pending"
    : !status.ollama_installed ? "pending"
    : status.ollama_running ? "done" : "active";
  const step3State: StepState = !status ? "pending"
    : !status.ollama_running ? "pending"
    : status.has_chat_model ? "done" : "active";
  const step4State: StepState = !status ? "pending"
    : !status.ollama_running ? "pending"
    : status.has_embed_model ? "done" : "active";

  const allDone = step1State === "done" && step2State === "done"
    && step3State === "done" && step4State === "done";

  const platformLabel = status ? (PLATFORM_LABEL[status.platform] || status.platform) : "";
  const downloadUrl = status ? (DOWNLOAD_URL[status.platform] || "https://ollama.com/download") : "";

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Models</h2>
        <p>Get your AI companion up and running. We'll walk you through every step.</p>
      </div>

      {/* ── Onboarding card ── */}
      <div className={`setup-card ${allDone ? "setup-card-done" : ""}`}>
        <div className="setup-card-header">
          <div>
            <h3>{allDone ? "✓ You're all set up" : "Get started"}</h3>
            <p className="caption dim">
              {statusLoading
                ? "Checking your system…"
                : status?.setup_complete
                ? `Ollama ${status.ollama_version} · ${status.models_total} model${status.models_total === 1 ? "" : "s"} installed`
                : "Four small steps. About 10 minutes depending on your connection."}
            </p>
          </div>
          <button
            className="ghost"
            onClick={() => setRecheckNonce((n) => n + 1)}
            title="Re-check everything"
          >
            ↻ Re-check
          </button>
        </div>

        {/* Step list */}
        <div className="setup-steps">
          <StepRow state={step1State} number={1} title="Install Ollama">
            {status?.ollama_installed ? (
              <span>Ollama {status.ollama_version} found{status.ollama_path ? ` at ${status.ollama_path}` : ""}.</span>
            ) : status && !status.ollama_installed ? (
              <div className="setup-step-actions">
                <span>Ollama is the local engine that runs your AI. Free, private, no account needed.</span>
                <a
                  href={downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="primary setup-cta"
                >
                  Download Ollama for {platformLabel} ↗
                </a>
                <span className="caption dim">
                  After downloading, run the installer and come back here. Then click Re-check.
                </span>
              </div>
            ) : null}
          </StepRow>

          <StepRow state={step2State} number={2} title="Start Ollama">
            {status?.ollama_running ? (
              <StatusDot ok={true} label="Ollama is running in the background." />
            ) : status && status.ollama_installed && !status.ollama_running ? (
              <div className="setup-step-actions">
                <span>Ollama is installed but not running. Click below to launch it.</span>
                <button className="primary setup-cta" onClick={launchOllama}>
                  ▶ Start Ollama
                </button>
                {status.platform === "linux" && (
                  <span className="caption dim">
                    On Linux, run <code>ollama serve</code> in a terminal.
                  </span>
                )}
              </div>
            ) : null}
          </StepRow>

          <StepRow state={step3State} number={3} title="Install a chat model">
            {status?.has_chat_model ? (
              <StatusDot ok={true} label={`You have at least one chat model installed (${status.models_total} total).`} />
            ) : status && status.ollama_running && reco ? (
              <div className="setup-step-actions">
                <span>
                  This is the AI that powers your companion's brain.{" "}
                  <strong>{reco.chat.label}</strong> ({reco.chat.size}) — {reco.chat.why}
                </span>
                <div className="row">
                  <button
                    className="primary setup-cta"
                    disabled={!!Object.values(activeJobs).find((j) => j.model === reco.chat.name)}
                    onClick={() => startInstall(reco.chat.name)}
                  >
                    {Object.values(activeJobs).find((j) => j.model === reco.chat.name)
                      ? "Installing…"
                      : `⬇ Install ${reco.chat.label}`}
                  </button>
                  {reco.chat.fallback_name && (
                    <button
                      className="ghost"
                      disabled={!!Object.values(activeJobs).find((j) => j.model === reco.chat.fallback_name)}
                      onClick={() => startInstall(reco.chat.fallback_name!)}
                      title={reco.chat.fallback_why}
                    >
                      Smaller? Try {reco.chat.fallback_label} ({reco.chat.fallback_size})
                    </button>
                  )}
                </div>
              </div>
            ) : null}
          </StepRow>

          <StepRow state={step4State} number={4} title="Install a memory model">
            {status?.has_embed_model ? (
              <StatusDot ok={true} label="Memory model installed — companions will remember across sessions." />
            ) : status && status.ollama_running && reco ? (
              <div className="setup-step-actions">
                <span>
                  Powers memory search. Tiny ({reco.embedding.size}).{" "}
                  <strong>{reco.embedding.label}</strong> — {reco.embedding.why}
                </span>
                <button
                  className="primary setup-cta"
                  disabled={!!Object.values(activeJobs).find((j) => j.model === reco.embedding.name)}
                  onClick={() => startInstall(reco.embedding.name)}
                >
                  {Object.values(activeJobs).find((j) => j.model === reco.embedding.name)
                    ? "Installing…"
                    : `⬇ Install ${reco.embedding.label}`}
                </button>
              </div>
            ) : null}
          </StepRow>
        </div>

        {/* Active install jobs */}
        {Object.values(activeJobs).length > 0 && (
          <div className="setup-active-jobs">
            <div className="setup-active-jobs-title">Installing right now</div>
            {Object.values(activeJobs).map((job) => (
              <div key={job.id} className="pull-job">
                <div className="pull-job-header">
                  <div className="pull-job-model">
                    <span className="spinner" />
                    <strong>{job.model}</strong>
                  </div>
                  <button className="ghost small" onClick={() => cancelJob(job.id)}>
                    Cancel
                  </button>
                </div>
                <ProgressBar pct={job.progress_pct} status={job.status} />
                {job.layers.length > 0 && (
                  <div className="pull-job-layers">
                    {job.layers.map((l, i) => (
                      <div key={i} className="pull-job-layer">
                        <span className="pull-job-layer-digest">{l.digest.slice(0, 20)}…</span>
                        <ProgressBar pct={l.pct} status={l.status} />
                      </div>
                    ))}
                  </div>
                )}
                <div className="caption dim">
                  {job.status === "pulling"
                    ? `Downloading… ${Math.round(job.elapsed_s)}s elapsed`
                    : job.status === "starting"
                    ? "Starting…"
                    : job.status}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* All-done celebration */}
        {allDone && (
          <div className="setup-done-banner">
            <div className="setup-done-mark">✦</div>
            <div>
              <div className="setup-done-title">Ready to chat</div>
              <div className="setup-done-text">
                Head to the Chat tab and pick a companion — or create a new one. Your local AI is good to go.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Catalog (power users) ── */}
      <div className="section">
        <div className="section-title">
          <h3>More models</h3>
          <span className="caption">For when you want to try something different</span>
        </div>

        <div className="models-filter">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              onClick={() => setFilter(c.id)}
              className={filter === c.id ? "active" : ""}
            >
              {c.label}
            </button>
          ))}
        </div>

        {catalogLoading ? (
          <div className="col" style={{ gap: 12 }}>
            {[1, 2, 3].map((i) => (
              <div key={i} className="card" style={{ padding: 20 }}>
                <div className="skeleton skeleton-line medium" style={{ height: 16, marginBottom: 10 }} />
                <div className="skeleton skeleton-line long" />
                <div className="skeleton skeleton-line long" />
              </div>
            ))}
          </div>
        ) : (
          <div className="models-grid">
            {filtered.map((model) => {
              const isActive = Object.values(activeJobs).find((j) => j.model === model.name);
              return (
                <div key={model.name} className={`model-card ${model.installed ? "installed" : ""}`}>
                  <div className="model-card-header">
                    <div className="model-card-title">
                      <span className="model-label">{model.label}</span>
                      <span className={`tag ${model.installed ? "success" : "muted"}`}>
                        {model.installed ? "✓ Installed" : "Not installed"}
                      </span>
                      {model.installed_size && (
                        <span className="tag muted">~{Math.round(model.installed_size / 1e9)}GB</span>
                      )}
                    </div>
                    <span className="tag muted">
                      {model.category === "chat" ? "Chat" : model.category === "embedding" ? "Memory" : "Art"}
                    </span>
                  </div>

                  <p className="model-desc">{model.description}</p>
                  {model.why && <p className="model-why">→ {model.why}</p>}

                  <div className="model-specs">
                    <span className="model-spec">
                      <span className="model-spec-label">Size</span> {model.size}
                    </span>
                    <span className="model-spec">
                      <span className="model-spec-label">RAM</span> {model.ram_needed}
                    </span>
                    <span className="model-spec">
                      <span className="model-spec-label">GPU</span> {model.gpu}
                    </span>
                  </div>

                  {!model.installed && (
                    <>
                      <div className="model-install">
                        <code>{model.pull_cmd}</code>
                        <div className="model-install-actions">
                          <button onClick={() => copy(model.pull_cmd)}>
                            {copied === model.pull_cmd ? "✓ Copied" : "Copy"}
                          </button>
                          <button
                            className="primary"
                            disabled={!!isActive}
                            onClick={() => startInstall(model.name)}
                          >
                            {isActive ? "Installing…" : "⬇ Install"}
                          </button>
                          <a href={model.url} target="_blank" rel="noreferrer" className="ghost" style={{ padding: "7px 14px", textDecoration: "none" }}>
                            View ↗
                          </a>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="models-info">
        <strong>What is Ollama?</strong> The local engine that runs AI models on your machine.{" "}
        Your data never leaves your computer. No account, no subscription, no telemetry.{" "}
        <a href="https://ollama.com" target="_blank" rel="noreferrer">Learn more ↗</a>
      </div>
    </div>
  );
}
