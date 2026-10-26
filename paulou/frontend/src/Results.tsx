import { hintsFor } from "./hints";
import { Legend, PhonemeStrip } from "./PhonemeStrip";
import type { Attempt, Sentence, UnitResult } from "./types";

function unitLabel(sentence: Sentence, unitId: string): string {
  for (const chunk of sentence.chunks) {
    const unit = chunk.units.find((u) => u.id === unitId);
    if (unit) return unit.words.join(" ");
  }
  return unitId;
}

// A whole-sentence attempt returns one result per unit across all chunks;
// group them under the chunk they belong to so the learner can see where in
// the sentence things went wrong.
function groupByChunk(sentence: Sentence, results: UnitResult[]) {
  return sentence.chunks
    .map((chunk) => ({
      chunk,
      results: results.filter((r) => chunk.units.some((u) => u.id === r.unit_id)),
    }))
    .filter((group) => group.results.length > 0);
}

export function Results({
  attempt,
  sentence,
  recordingUrl,
}: {
  attempt: Attempt;
  sentence: Sentence;
  recordingUrl: string | null;
}) {
  const card = (result: UnitResult) => (
    <UnitResultCard
      key={result.unit_id}
      result={result}
      label={unitLabel(sentence, result.unit_id)}
      calibrated={attempt.calibrated}
    />
  );
  return (
    <section className="results" aria-label="Result">
      {recordingUrl && (
        <div className="own-recording">
          <span aria-hidden="true">🎧</span>
          <audio controls src={recordingUrl} aria-label="Your recording" />
        </div>
      )}
      <Legend />
      {attempt.whole_sentence
        ? groupByChunk(sentence, attempt.results).map(({ chunk, results }) => (
            <div key={chunk.index} className="result-group" role="group" aria-label={`Chunk ${chunk.index + 1}: ${chunk.text}`}>
              <h3 className="result-group-title" lang="fr">
                <span className="tab-num" aria-hidden="true">
                  {chunk.index + 1}
                </span>
                {chunk.text}
              </h3>
              {results.map(card)}
            </div>
          ))
        : attempt.results.map(card)}
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
      <h4>{label}</h4>
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
