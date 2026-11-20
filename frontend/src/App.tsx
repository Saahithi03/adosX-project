import { useEffect, useState } from "react";
import { api } from "./api";
import type { Me } from "./types";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";

// Top level: are we logged in? GET /api/me answers that (and hands us the
// CSRF cookie that the login POST needs).
export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = still checking
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => setError("Can't reach the server. Is `make dev` running?"));
  }, []);

  if (error) return <p className="page-message error">{error}</p>;
  if (me === undefined) return <p className="page-message">Loading…</p>;
  if (me === null) return <Login onLoggedIn={setMe} />;

  async function logout() {
    await api.logout();
    setMe(null);
  }

  // key: a different user gets a fresh Dashboard, with no state left over.
  return <Dashboard key={me.username} me={me} onLogout={logout} />;
}
