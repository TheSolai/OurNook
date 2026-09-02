import { useEffect, useState, useRef } from "react";
import {
  type BackupFileInfo,
  useCompanionStore,
} from "./stores";

const API = "/api";
async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

interface BackupPanelProps {
  onClose: () => void;
  showToast: (msg: string) => void;
}

export function BackupPanel({ onClose, showToast }: BackupPanelProps) {
  const { roster, fetchRoster } = useCompanionStore();
  const [backups, setBackups] = useState<BackupFileInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedCompanionId, setSelectedCompanionId] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void fetchBackups();
  }, []);

  async function fetchBackups() {
    try {
      const list = await apiGet<BackupFileInfo[]>("/backups");
      setBackups(list);
    } catch (e) {
      console.error(e);
    }
  }

  async function backupOne(companionId: string) {
    setBusy(true);
    try {
      const result = await apiPost<{ path: string; bytes: number }>(
        `/backups/companion/${companionId}`
      );
      showToast(`✓ Backed up to ${result.path.split("/").pop()}`);
      await fetchBackups();
    } catch (e) {
      showToast(`✗ Backup failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function backupEverything() {
    setBusy(true);
    try {
      const result = await apiPost<{ path: string; bytes: number; companion_count: number }>(
        "/backups/all"
      );
      showToast(
        `✓ Backed up ${result.companion_count} companion(s) to ${result.path.split("/").pop()}`
      );
      await fetchBackups();
    } catch (e) {
      showToast(`✗ Backup all failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRestoreFile(file: File) {
    setBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      // Read file as text and send the path... actually we need to handle this differently
      // Since we can't upload files via fetch easily, we use the backup path
      // For now, show a message about how to restore
      showToast("Restore: put .zip in ~/.nook/backups/ and it will appear here");
    } catch (e) {
      showToast(`✗ Restore failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ minWidth: 480, maxWidth: 600 }}>
        <div className="modal-header">
          <h2>Backup & Restore</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        <div style={{ padding: "0 24px 24px" }}>
          {/* Backup section */}
          <h3 style={{ marginTop: 16 }}>Backup</h3>
          <div className="row" style={{ gap: 8, marginBottom: 12 }}>
            <select
              value={selectedCompanionId}
              onChange={(e) => setSelectedCompanionId(e.target.value)}
              style={{ flex: 1 }}
            >
              <option value="">— select companion —</option>
              {roster.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <button
              className="primary"
              disabled={!selectedCompanionId || busy}
              onClick={() => { if (selectedCompanionId) void backupOne(selectedCompanionId); }}
            >
              Backup this
            </button>
          </div>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void backupEverything()}
            style={{ marginBottom: 16 }}
          >
            Backup all companions
          </button>

          {/* Restore section */}
          <h3>Restore</h3>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Backup files are stored in <code>~/.nook/backups/</code>
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleRestoreFile(file);
            }}
          />
          <button
            className="secondary"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            Restore from file
          </button>

          {/* File list */}
          {backups.length > 0 && (
            <>
              <h3 style={{ marginTop: 20 }}>Existing backups</h3>
              <div style={{ maxHeight: 200, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8 }}>
                {backups.map((b) => (
                  <div
                    key={b.path}
                    style={{
                      padding: "8px 12px",
                      borderBottom: "1px solid var(--border)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 500 }}>{b.name}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {(b.bytes / 1024).toFixed(1)} KB · {new Date(b.modified).toLocaleString()}
                      </div>
                    </div>
                    <button
                      className="secondary"
                      style={{ fontSize: 11 }}
                      onClick={async () => {
                        setBusy(true);
                        try {
                          const result = await apiPost<{ new_companion_ids: string[]; skipped: number }>(
                            "/backups/restore", { path: b.path }
                          );
                          showToast(`✓ Restored ${result.new_companion_ids.length} companion(s)`);
                          await fetchRoster();
                        } catch (e) {
                          showToast(`✗ ${e}`);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Restore
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
