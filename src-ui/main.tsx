import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./i18n";
import "./styles.css";

// Debug: confirm this file is loading
console.log("[OurNook] main.tsx loaded - React starting");

// Show debug indicator immediately so we know the JS bundle loaded
const root = document.getElementById("root");
if (root) {
  root.innerHTML = '<div style="position:fixed;inset:0;background:#1a1a2e;color:#f0a4c0;display:flex;align-items:center;justify-content:center;font-family:system-ui;font-size:18px;z-index:99999;flex-direction:column;gap:12px;"><div>OurNook is loading...</div><div id="load-status" style="font-size:13px;color:#9aa0a6;">Checking assets...</div></div>';
  const status = document.getElementById("load-status");
  if (status) {
    status.textContent = "main.tsx loaded ✓ — React rendering...";
  }
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
