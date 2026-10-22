import { FormEvent, useRef, useState } from "react";
import { ApiError, createSentence } from "./api";
import { Loading } from "./Loading";
import { Practice } from "./Practice";
import type { Sentence } from "./types";
import { useHealth } from "./useHealth";

const EXAMPLES = ["Les enfants ont acheté des pommes.", "Je voudrais un petit café, s'il vous plaît."];
const MAX_CHARS = 300;

export function App() {
  const health = useHealth();
  const [text, setText] = useState("");
  const [sentence, setSentence] = useState<Sentence | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const prepare = async (value: string) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setPreparing(true);
    setError(null);
    try {
      setSentence(await createSentence(value, controller.signal));
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setSentence(null);
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      if (abort.current === controller) setPreparing(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim()) void prepare(text);
  };

  const cancel = () => {
    abort.current?.abort();
    setPreparing(false);
  };

  return (
    <main className="app">
      <header className="top">
        <h1>Paulou</h1>
        <p className="tagline">Practice any French sentence, one rhythm group at a time.</p>
        {health === null && <p className="status">Connecting to the server…</p>}
        {health?.status === "warming_up" && <p className="status">Loading the speech model…</p>}
      </header>

      {preparing ? (
        <Loading onCancel={cancel} />
      ) : sentence ? (
        <>
          <button type="button" className="btn btn-soft new-sentence" onClick={() => setSentence(null)}>
            New sentence
          </button>
          <Practice
            key={sentence.sentence_id}
            sentence={sentence}
            health={health}
            onExpired={() => void prepare(sentence.text)}
          />
        </>
      ) : (
        <form className="glass input-card" onSubmit={submit}>
          <label htmlFor="sentence">Which sentence do you want to say?</label>
          <textarea
            id="sentence"
            lang="fr"
            rows={3}
            maxLength={MAX_CHARS}
            value={text}
            placeholder="Type or paste a French sentence"
            onChange={(e) => setText(e.target.value)}
          />
          <div className="row spread">
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" className="chip" lang="fr" onClick={() => setText(example)}>
                  {example}
                </button>
              ))}
            </div>
            <button type="submit" className="btn btn-primary" disabled={!text.trim()}>
              <span aria-hidden="true">✨</span> Prepare
            </button>
          </div>
          {error && (
            <p className="note warn" role="alert">
              {error}
            </p>
          )}
        </form>
      )}
    </main>
  );
}
