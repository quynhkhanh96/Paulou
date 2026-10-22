import { hintsFor } from "./hints";
import { Legend, PhonemeStrip } from "./PhonemeStrip";
import type { Attempt, Chunk, UnitResult } from "./types";

function unitLabel(chunk: Chunk, unitId: string): string {
  const unit = chunk.units.find((u) => u.id === unitId);
  return unit ? unit.words.join(" ") : unitId;
}

export function Results({
  attempt,
  chunk,
  recordingUrl,
}: {
  attempt: Attempt;
  chunk: Chunk;
  recordingUrl: string | null;
}) {
  return (
    <section className="results" aria-label="Result">
      {recordingUrl && (
        <div className="own-recording">
          <span aria-hidden="true">🎧</span>
          <audio controls src={recordingUrl} aria-label="Your recording" />
        </div>
      )}
      <Legend />
      {attempt.results.map((result) => (
        <UnitResultCard key={result.unit_id} result={result} label={unitLabel(chunk, result.unit_id)} calibrated={attempt.calibrated} />
      ))}
      <p className="note">
        Results come from an early model. Sounds linking to the next chunk, optional vowels and sounds next to nasal
        vowels can be marked wrongly.
      </p>
    </section>
  );
}

function UnitResultCard({ result, label, calibrated }: { result: UnitResult; label: string; calibrated: boolean }) {
  const hints = hintsFor(result);
  return (
    <article className="glass unit-result">
      <h3>{label}</h3>
      <PhonemeStrip ops={result.ops} />
      <p className="feedback">{result.feedback_text}</p>
      {!calibrated && (
        <p className="note">The overall wording ("good effort", "needs work") is a placeholder until scoring is calibrated.</p>
      )}
      {hints.map((hint) => (
        <p key={hint} className="note hint">
          {hint}
        </p>
      ))}
    </article>
  );
}
