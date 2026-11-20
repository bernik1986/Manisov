import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider, useAuth } from "../src/context/AuthContext.jsx";
import * as api from "../src/api.js";
import * as drafts from "../src/utils/documentIntakeDrafts.js";

window.authTest = { api, drafts, mounts: 0, results: {} };
window.authTest.start = (name, path, config) => {
  api.apiClient.get(path, config).then(
    response => { window.authTest.results[name] = { ok: true, data: response.data }; },
    error => { window.authTest.results[name] = { ok: false, code: error.code }; },
  );
};

function PrivatePanel() {
  const { user } = useAuth();
  const [mount] = useState(() => ++window.authTest.mounts);
  const [correction, setCorrection] = useState("");
  return <section data-testid="private-panel">
    <output data-testid="private-mount">{mount}</output>
    <output data-testid="private-user">{user.username}</output>
    <output data-testid="private-role">{user.role}</output>
    <input aria-label="Unsaved correction" value={correction} onChange={event => setCorrection(event.target.value)} />
  </section>;
}

function Harness() {
  const auth = useAuth();
  useEffect(() => { window.authTest.auth = auth; }, [auth]);
  return <main>
    <output data-testid="token">{auth.token || ""}</output>
    {auth.isAuthenticated ? <PrivatePanel /> : <h1>Signed out</h1>}
    <button onClick={auth.logout}>Sign out</button>
  </main>;
}

createRoot(document.getElementById("root")).render(<AuthProvider><Harness /></AuthProvider>);
