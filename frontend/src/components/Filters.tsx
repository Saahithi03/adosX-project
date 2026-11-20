import type { LocationOption, ReasonOption } from "../types";

export interface FilterValues {
  reason: string; // "" = all
  location: string; // "" = all
}

interface Props {
  reasons: ReasonOption[];
  locations: LocationOption[]; // already only this org's, from /api/locations
  value: FilterValues;
  onChange: (next: FilterValues) => void;
}

export default function Filters({ reasons, locations, value, onChange }: Props) {
  return (
    <div className="filters">
      <label>
        Reason
        <select value={value.reason} onChange={(e) => onChange({ ...value, reason: e.target.value })}>
          <option value="">All reasons</option>
          {reasons.map((r) => (
            <option key={r.code} value={r.code}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Location
        <select value={value.location} onChange={(e) => onChange({ ...value, location: e.target.value })}>
          <option value="">All locations</option>
          {locations.map((l) => (
            <option key={l.location_id} value={l.location_id}>
              {l.location_name}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
