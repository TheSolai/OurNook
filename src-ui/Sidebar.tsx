import { useEffect, useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useCompanionStore, useStatusStore, useUIStore } from "./stores";

const AVATAR_COLORS: Record<string, string> = {
  mira:  "linear-gradient(135deg, #b87fd4, #7f6ed4)",
  sable: "linear-gradient(135deg, #6e9a7a, #3d5a4a)",
  finn:  "linear-gradient(135deg, #8aa8c8, #4a7a9a)",
};

function getAvatarStyle(avatarPath: string | null, name: string): React.CSSProperties {
  if (avatarPath && avatarPath.startsWith("bundled:")) {
    const key = avatarPath.replace("bundled:", "");
    return { background: AVATAR_COLORS[key] || "linear-gradient(135deg, #b8a0c0, #8a7a98)" };
  }
  // Generate a sophisticated gradient from the name's first letter
  const hue = (name.charCodeAt(0) * 137) % 360;
  return { background: `linear-gradient(135deg, hsl(${hue}, 40%, 48%), hsl(${(hue + 35) % 360}, 35%, 38%))` };
}

export function Sidebar() {
  const { t } = useTranslation();
  const { roster, activeId, setActive, fetchRoster, remove } = useCompanionStore();
  const { ollama } = useStatusStore();
  const openWizard = useUIStore((s) => s.openWizard);
  const openEditor = useUIStore((s) => s.openEditor);

  const [search, setSearch] = useState("");
  useEffect(() => { void fetchRoster(); }, [fetchRoster]);

  // Filter the roster by search term (case-insensitive name match)
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return roster;
    return roster.filter((c) => c.name.toLowerCase().includes(q));
  }, [roster, search]);

  return (
    <div className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-logo">
          <img src="/icons/brand.svg" alt="" className="sidebar-brand-mark" />
          OurNook
        </div>
        <div className="sidebar-brand-tag">Your private companion hub</div>
      </div>

      <div className="sidebar-status">
        <span className={`dot ${ollama?.healthy ? "ok" : ollama === null ? "warn" : "err"}`} />
        <span>{ollama?.healthy ? "Ollama online" : "Ollama offline"}</span>
      </div>

      <div className="sidebar-roster">
        <div className="sidebar-section-label">
          Companions {filtered.length !== roster.length && (
            <span className="caption dim">({filtered.length}/{roster.length})</span>
          )}
        </div>
        {roster.length > 4 && (
          <div className="sidebar-search">
            <input
              type="search"
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="sidebar-search-input"
            />
            {search && (
              <button className="sidebar-search-clear" onClick={() => setSearch("")} title="Clear search" aria-label="Clear search">
                ×
              </button>
            )}
          </div>
        )}
        {roster.length === 0 ? (
          <p className="caption dim" style={{ padding: "8px 10px" }}>No companions yet.</p>
        ) : filtered.length === 0 ? (
          <p className="caption dim" style={{ padding: "8px 10px" }}>No matches.</p>
        ) : (
          <div className="companion-list">
            {filtered.map((c) => (
              <div
                key={c.id}
                className={`companion-item-wrap ${c.id === activeId ? "active" : ""}`}
              >
                <button
                  className={`companion-item ${c.id === activeId ? "active" : ""}`}
                  onClick={() => setActive(c.id)}
                  title={c.name}
                >
                  <div className="companion-avatar" style={getAvatarStyle(c.avatar_path, c.name)}>
                    {c.name.slice(0, 1).toUpperCase()}
                  </div>
                  <span className="companion-item-name">{c.name}</span>
                </button>
                <button
                  className="companion-edit-btn ghost"
                  onClick={(e) => { e.stopPropagation(); openEditor(c.id); }}
                  title={`Edit ${c.name}`}
                >
                  ✎
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="sidebar-footer">
        <button className="primary" onClick={openWizard}>
          ✦ New companion
        </button>
        {activeId && (
          <button
            className="danger"
            onClick={async () => {
              const target = roster.find((c) => c.id === activeId);
              if (!target) return;
              // Real delete safety: type the companion's name to confirm.
              // A simple OK/cancel is too easy to mis-click — too much data lost.
              const expected = target.name;
              const typed = window.prompt(
                `Permanently delete ${expected}? This removes all memories, messages, and diary entries.\n\nType "${expected}" to confirm:`
              );
              if (typed === null) return; // cancelled
              if (typed.trim() !== expected) {
                useUIStore.getState().showToast("Name didn't match — delete cancelled", "err");
                return;
              }
              try {
                await remove(activeId);
                useUIStore.getState().showToast(`Deleted ${expected}`, "ok");
              } catch (e) {
                useUIStore.getState().showToast(`✗ ${e}`, "err");
              }
            }}
          >
            {t("companion.delete") || "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}
