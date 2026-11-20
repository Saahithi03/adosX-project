import { useEffect, useState } from "react";
import { api } from "../api";
import type { ExceptionItem, LocationOption, Me, ReasonOption } from "../types";
import Header from "./Header";
import Filters, { type FilterValues } from "./Filters";
import ExceptionsTable from "./ExceptionsTable";
import AskPanel from "./AskPanel";

const NO_FILTERS: FilterValues = { reason: "", location: "" };

export default function Dashboard({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [reasons, setReasons] = useState<ReasonOption[]>([]);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [filters, setFilters] = useState<FilterValues>(NO_FILTERS);
  const [items, setItems] = useState<ExceptionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState<string | null>(null);

  // An Ask chip was clicked. If the current filters hide that record, clear
  // them so the row is there to see; the effect below then scrolls to it.
  function showRecord(recordId: string) {
    setHighlighted(recordId);
    if (items && !items.some((i) => i.record_id === recordId)) setFilters(NO_FILTERS);
  }

  useEffect(() => {
    if (!highlighted || !items) return;
    document.querySelector(`tr[data-record="${CSS.escape(highlighted)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlighted, items]);

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
        <AskPanel onRecordClick={showRecord} />
        <Filters
          reasons={reasons}
          locations={locations}
          value={filters}
          onChange={(next) => {
            setHighlighted(null);
            setFilters(next);
          }}
        />
        {error && <p className="error">{error}</p>}
        {items === null ? <p className="empty">Loading…</p> : <ExceptionsTable items={items} highlighted={highlighted} />}
        {items && <p className="count">{items.length === 1 ? "1 exception" : `${items.length} exceptions`}</p>}
      </main>
    </>
  );
}
