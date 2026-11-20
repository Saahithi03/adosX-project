// Shapes returned by the Django API (CLAUDE.md §6–7).

export interface Me {
  username: string;
  org_id: string;
}

export interface ExceptionItem {
  record_id: string;
  location_id: string;
  location_name: string;
  reason_code: string;
  reason_label: string;
  a_amount: string | null; // decimal string, e.g. "138948.30"; null = no A record
  b_amount: string | null; // null = no B entry, or a blank B amount
  b_entry_ids: string[];
}

export interface LocationOption {
  location_id: string;
  location_name: string;
}

export interface ReasonOption {
  code: string;
  label: string;
}
