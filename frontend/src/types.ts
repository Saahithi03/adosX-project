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

// POST /api/ask returns one of these two shapes (CLAUDE.md §8).
export interface AskAnswered {
  answered: true;
  answer: string; // built by the server from a template, never by the model
  value: number | string | Record<string, number | string>;
  evidence: string[]; // record IDs every number was computed from
  excluded?: string[]; // sum_gap only: records left out, named in the answer
}

export interface AskRefused {
  answered: false;
  reason_code: string;
  reason: string; // one of the server's fixed messages; contains no numbers
}

export type AskResult = AskAnswered | AskRefused;
