import { useEffect, useRef, useState } from "react";
import { ApiError, audioUrl, createAttempt } from "./api";
import { PlayButton } from "./PlayButton";
import { RecordButton } from "./Recorder";
import { Results } from "./Results";
import type { Attempt, Health, Sentence, Target } from "./types";
import { useRecorder } from "./useRecorder";

interface Props {
  sentence: Sentence;
  health: Health | null;
  onExpired: () => void;
}

const UNIT_KIND: Record<string, string> = {
  liaison_group: "liaison",
  elision_group: "elision",
};

export function Practice({ sentence, health, onExpired }: Props) {
  const [chunkIndex, setChunkIndex] = useState(0);
  const [unitId, setUnitId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const recorder = useRecorder();
  const lastUrl = useRef<string | null>(null);

  const chunk = sentence.chunks[chunkIndex];
  const target: Target = unitId ? { kind: "unit", unitId } : { kind: "chunk", chunkIndex };

  useEffect(
    () => () => {
      if (lastUrl.current) URL.revokeObjectURL(lastUrl.current);
    },
    [],
  );

  const reset = () => {
    setAttempt(null);
    setError(null);
  };
  const chooseChunk = (index: number) => {
    setChunkIndex(index);
    setUnitId(null);
    reset();
  };
  const chooseUnit = (id: string | null) => {
    setUnitId(id);
    reset();
  };

  const stopAndScore = async () => {
    const blob = await recorder.stop();
    if (!blob || blob.size === 0) return;
    if (lastUrl.current) URL.revokeObjectURL(lastUrl.current);
    lastUrl.current = URL.createObjectURL(blob);
    setRecordingUrl(lastUrl.current);
    setBusy(true);
    setError(null);
    try {
      setAttempt(await createAttempt(sentence.sentence_id, target, blob));
    } catch (e) {
      setAttempt(null);
      setError(e instanceof ApiError ? e : new ApiError(0, "unknown", "Something went wrong. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const modelReady = health?.status === "ready";
  const unit = unitId ? chunk.units.find((u) => u.id === unitId) : null;
  const clipTarget: Target = target;

  return (
    <div className="practice">
      <section className="glass sentence-card">
        <p className="sentence-text" lang="fr">
          {sentence.text}
        </p>
        <div className="row">
          <PlayButton src={audioUrl(sentence.sentence_id, "normal")} label="Whole sentence" emoji="🔊" />
          <PlayButton src={audioUrl(sentence.sentence_id, "slow")} label="Whole sentence, slowly" emoji="🐢" />
        </div>
      </section>

      <nav className="chunk-tabs" aria-label="Chunks">
        {sentence.chunks.map((c) => (
          <button
            key={c.index}
            type="button"
            className={`chip ${c.index === chunkIndex ? "is-active" : ""}`}
            aria-current={c.index === chunkIndex ? "true" : undefined}
            onClick={() => chooseChunk(c.index)}
            lang="fr"
          >
            {c.text}
          </button>
        ))}
      </nav>

      <section className="glass chunk-card" aria-label={`Practice: ${chunk.text}`}>
        <div className="row">
          <PlayButton src={audioUrl(sentence.sentence_id, "normal", clipTarget)} label="Listen" emoji="🔊" />
          <PlayButton src={audioUrl(sentence.sentence_id, "slow", clipTarget)} label="Listen slowly" emoji="🐢" />
        </div>

        <div className="units" role="group" aria-label="Practice a single word or link">
          <button type="button" className={`unit ${unitId === null ? "is-active" : ""}`} onClick={() => chooseUnit(null)}>
            <span className="unit-words">Whole chunk</span>
          </button>
          {chunk.units.map((u) => (
            <button
              key={u.id}
              type="button"
              className={`unit ${u.id === unitId ? "is-active" : ""}`}
              onClick={() => chooseUnit(u.id)}
              aria-pressed={u.id === unitId}
            >
              <span className="unit-words" lang="fr">
                {u.words.join(" ")}
              </span>
              <span className="unit-ipa">/{u.ipa}/</span>
              {UNIT_KIND[u.type] && (
                <span className="unit-kind">
                  {UNIT_KIND[u.type]}
                  {u.liaison_consonant ? ` /${u.liaison_consonant}/` : ""}
                </span>
              )}
            </button>
          ))}
        </div>

        {!modelReady && health?.status !== "error" && (
          <p className="note">The speech model is still loading. Recording unlocks in a few seconds.</p>
        )}
        {health?.status === "error" && (
          <p className="note warn" role="alert">
            The speech model could not start. Check the server log.
          </p>
        )}

        <RecordButton
          state={recorder.state}
          disabled={!modelReady}
          busy={busy}
          onStart={() => void recorder.start()}
          onStop={() => void stopAndScore()}
          idleLabel={unit ? `Record "${unit.words.join(" ")}"` : "Record this chunk"}
        />

        {error && (
          <div className="note warn" role="alert">
            <p>{error.message}</p>
            {error.code === "sentence_not_found" && (
              <button type="button" className="btn btn-soft" onClick={onExpired}>
                Prepare again
              </button>
            )}
          </div>
        )}
      </section>

      {attempt && <Results attempt={attempt} chunk={chunk} recordingUrl={recordingUrl} />}
    </div>
  );
}
