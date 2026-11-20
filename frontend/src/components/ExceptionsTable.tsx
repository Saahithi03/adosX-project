import { formatINR } from "../format";
import type { ExceptionItem } from "../types";

interface Props {
  items: ExceptionItem[];
  highlighted?: string | null; // record ID picked from an Ask answer
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
            <td className="num">{formatINR(x.a_amount)}</td>
            <td className="num" title={x.b_entry_ids.join(", ") || "No accounts entry"}>
              {formatINR(x.b_amount)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
