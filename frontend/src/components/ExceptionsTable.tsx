import { formatINR } from "../format";
import type { ExceptionItem } from "../types";

interface Props {
  items: ExceptionItem[];
  highlighted?: string | null; // record ID picked from an Ask answer
}

// A null amount means different things, so say which instead of a bare "—":
//   System A null          -> there is no sale record (MISSING_IN_SYSTEM_A)
//   System B null, 0 IDs   -> accounts has no entry at all (e.g. REC-1061)
//   System B null, has IDs -> the entry exists but its amount is blank (REC-1050)
function SystemAAmount({ item }: { item: ExceptionItem }) {
  if (item.a_amount !== null) return <>{formatINR(item.a_amount)}</>;
  return (
    <span className="missing missing-none" title="System A has no sale with this record ID">
      No sale record
    </span>
  );
}

function SystemBAmount({ item }: { item: ExceptionItem }) {
  if (item.b_amount !== null) return <>{formatINR(item.b_amount)}</>;
  if (item.b_entry_ids.length === 0) {
    return (
      <span className="missing missing-none" title="Accounts has no entry for this sale">
        No entry
      </span>
    );
  }
  return (
    <span className="missing missing-blank" title={`Entry ${item.b_entry_ids.join(", ")} has no amount`}>
      Amount blank
    </span>
  );
}

export default function ExceptionsTable({ items, highlighted = null }: Props) {
  if (items.length === 0) return <p className="empty">No exceptions match these filters.</p>;

  return (
    <table className="exceptions">
      <thead>
        <tr>
          <th>Record</th>
          <th>Location</th>
          <th>Reason</th>
          <th className="num">System A</th>
          <th className="num">System B</th>
        </tr>
      </thead>
      <tbody>
        {items.map((x) => (
          // data-record lets the Dashboard scroll an Ask chip's row into view.
          <tr
            key={`${x.record_id}-${x.reason_code}`}
            data-record={x.record_id}
            className={x.record_id === highlighted ? "highlight" : undefined}
          >
            <td className="mono">{x.record_id}</td>
            <td>{x.location_name}</td>
            <td title={x.reason_code}>{x.reason_label}</td>
            <td className="num">
              <SystemAAmount item={x} />
            </td>
            <td className="num" title={x.b_entry_ids.join(", ") || undefined}>
              <SystemBAmount item={x} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
