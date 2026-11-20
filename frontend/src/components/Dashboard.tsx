import { useEffect, useState } from "react";
import { api } from "../api";
import type { ExceptionItem, LocationOption, Me, ReasonOption } from "../types";
import Header from "./Header";
import Filters, { type FilterValues } from "./Filters";
import ExceptionsTable from "./ExceptionsTable";

export default function Dashboard({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [reasons, setReasons] = useState<ReasonOption[]>([]);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [filters, setFilters] = useState<FilterValues>({ reason: "", location: "" });
  const [items, setItems] = useState<ExceptionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Dropdown options, once.
  useEffect(() => {
    Promise.all([api.reasons(), api.locations()])
      .then(([r, l]) => {
        setReasons(r);
        setLocations(l);
      })
      .catch((e) => setError(e.message));
  }, []);

  // The list, re-fetched from the server whenever a filter changes.
  useEffect(() => {
    let stale = false; // ignore a slow response that a newer filter overtook
    setItems(null);
    api
      .exceptions(filters)
      .then((data) => {
        if (stale) return;
        setItems(data);
        setError(null);
      })
      .catch((e) => {
        if (!stale) setError(e.message);
      });
    return () => {
      stale = true;
    };
  }, [filters]);

  return (
    <>
      <Header me={me} onLogout={onLogout} />
      <main>
        {/* AskPanel goes here in step 11. */}
        <Filters reasons={reasons} locations={locations} value={filters} onChange={setFilters} />
        {error && <p className="error">{error}</p>}
        {items === null ? <p className="empty">Loading…</p> : <ExceptionsTable items={items} />}
        {items && <p className="count">{items.length === 1 ? "1 exception" : `${items.length} exceptions`}</p>}
      </main>
    </>
  );
}
