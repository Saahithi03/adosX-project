import type { Me } from "../types";

// The org is display-only. Nothing in the UI can change or send it.
export default function Header({ me, onLogout }: { me: Me; onLogout: () => void }) {
  return (
    <header className="header">
      <strong>Reconciliation exceptions</strong>
      <span className="who">
        {me.username} · {me.org_id}
      </span>
      <button type="button" onClick={onLogout}>
        Log out
      </button>
    </header>
  );
}
