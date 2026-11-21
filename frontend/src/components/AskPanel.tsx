import { useRef, useState, type FormEvent } from "react";
import Backdrop from "@mui/material/Backdrop";
import CircularProgress from "@mui/material/CircularProgress";
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
  const inputRef = useRef<HTMLInputElement>(null);

  // Empties the question box only; the last answer stays on screen.
  function clearQuestion() {
    setQuestion("");
    inputRef.current?.focus(); // ready to type the next question
  }

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
          ref={inputRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your exceptions, e.g. “How many at Location 103?”"
          maxLength={MAX_LENGTH}
          aria-label="Question"
        />
        <button type="submit" disabled={busy || !question.trim()}>
          Ask
        </button>
        <button
          type="button"
          className="danger"
          onClick={clearQuestion}
          disabled={busy || question === ""}
        >
          Clear
        </button>
      </form>

      {/* Full-page loader: the backdrop covers the page (and blocks clicks)
          until /api/ask responds. The free LLM tier can take several seconds. */}
      <Backdrop
        open={busy}
        sx={{
          color: "#fff",
          zIndex: (theme) => theme.zIndex.modal + 1,
          flexDirection: "column",
          gap: 2,
        }}
      >
        <CircularProgress color="inherit" aria-label="Loading" />
        <span role="status" aria-live="polite">
          Working out your answer…
        </span>
      </Backdrop>

      {error && <p className="error">{error}</p>}

      {result?.answered === true && (
        <div className="answer" role="status">
          <p>{result.answer}</p>
          {result.evidence.length > 0 && (
            <div className="chips" aria-label="Records this answer is based on">
              {result.evidence.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="chip"
                  onClick={() => onRecordClick(id)}
                  title="Show in table"
                >
                  {id}
                </button>
              ))}
            </div>
          )}
          {result.excluded && result.excluded.length > 0 && (
            <div
              className="chips muted"
              aria-label="Records left out of the total"
            >
              <span>Not included:</span>
              {result.excluded.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="chip"
                  onClick={() => onRecordClick(id)}
                >
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
