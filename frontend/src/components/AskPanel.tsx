import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { AskResult } from "../types";

interface Props {
  /** Called when a record-ID chip is clicked, to show that row in the table. */
  onRecordClick: (recordId: string) => void;
}

const MAX_LENGTH = 500; // same limit the server enforces

export default function AskPanel({ onRecordClick }: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null); // the loader replaces the previous answer while we wait
    try {
      setResult(await api.ask(question));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ask">
      <form onSubmit={submit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your exceptions, e.g. “How many at Location 103?”"
          maxLength={MAX_LENGTH}
          aria-label="Question"
        />
        <button type="submit" disabled={busy || !question.trim()}>
          {busy ? "Asking…" : "Ask"}
        </button>
      </form>

      {busy && (
        <div className="ask-loading" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          Working out your answer…
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {result?.answered === true && (
        <div className="answer" role="status">
          <p>{result.answer}</p>
          {result.evidence.length > 0 && (
            <div className="chips" aria-label="Records this answer is based on">
              {result.evidence.map((id) => (
                <button key={id} type="button" className="chip" onClick={() => onRecordClick(id)} title="Show in table">
                  {id}
                </button>
              ))}
            </div>
          )}
          {result.excluded && result.excluded.length > 0 && (
            <div className="chips muted" aria-label="Records left out of the total">
              <span>Not included:</span>
              {result.excluded.map((id) => (
                <button key={id} type="button" className="chip" onClick={() => onRecordClick(id)}>
                  {id}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* A refusal shows only the server's fixed message: no numbers, no model text. */}
      {result?.answered === false && (
        <div className="refusal" role="alert">
          <strong>Can't answer that.</strong> {result.reason}
        </div>
      )}
    </section>
  );
}
