import { useId, useState } from "react";
import { audioUrl } from "./api";
import { hintsFor } from "./hints";
import { HearYourself } from "./HearYourself";
import { buildUnitViews, firstToOpen, summarize, unitGood, type Finding, type UnitView } from "./learnerModel";
import { FindingText, TEXT, UnitGoodText } from "./learnerText";
import { PlayButton } from "./PlayButton";
import { TrackChanges, TrackLegend } from "./TrackChanges";
import type { Attempt, Sentence } from "./types";

// Learner result view (Decision Log D63): one score line, "Needs fixing" before
// "You did well", then one chip per word. A chip opens its card in place with
// the word's track-changes, its own two boxes and the two listen buttons.

interface Props {
  attempt: Attempt;
  sentence: Sentence;
  recording: Blob | null;
  recordingUrl: string | null;
}

export function LearnerResults({ attempt, sentence, recording, recordingUrl }: Props) {
  const views = buildUnitViews(sentence, attempt.results);
  const summary = summarize(views);
  const [opened, setOpened] = useState<{ id: string | null } | null>(null);
  const openId = opened ? opened.id : firstToOpen(views);
  const toggle = (id: string) => setOpened({ id: openId === id ? null : id });
  const base = useId();

  const groups = attempt.whole_sentence
    ? sentence.chunks
        .map((chunk) => ({ chunk, views: views.filter((v) => v.chunkIndex === chunk.index) }))
        .filter((g) => g.views.length > 0)
    : [{ chunk: null, views }];

  const chipRow = (rowViews: UnitView[]) => (
    <div className="wordrow" role="group" aria-label={TEXT.chipsLabel}>
      {rowViews.map((view) => {
        const open = view.unit.id === openId;
        const cardId = `${base}-card-${view.unit.id}`;
        return (
          <WordChip
            key={view.unit.id}
            view={view}
            open={open}
            cardId={cardId}
            onToggle={() => toggle(view.unit.id)}
            card={
              open && (
                <WordCard
                  id={cardId}
                  view={view}
                  sentenceId={sentence.sentence_id}
                  recording={recording}
                />
              )
            }
          />
        );
      })}
    </div>
  );

  return (
    <section className="results" aria-label="Result">
      {recordingUrl && (
        <div className="own-recording">
          <span aria-hidden="true">🎧</span>
          <audio controls src={recordingUrl} aria-label="Your recording" />
        </div>
      )}

      <div className="score">
        <span className="score-big">
          {summary.wordsOk}
          <small>
            /{summary.wordsTotal} {TEXT.wordsCorrect}
          </small>
        </span>{" "}
        <span className="score-sub">
          {summary.soundsOk}/{summary.soundsTotal} {TEXT.soundsCorrect}
          {summary.near > 0 && (
            <>
              {" · "}
              {summary.near} {TEXT.closeSounds}
            </>
          )}
        </span>
      </div>

      {(summary.fixes.length > 0 || summary.good.length > 0) && (
        <div className={`cols ${summary.fixes.length > 0 && summary.good.length > 0 ? "" : "single"}`}>
          {summary.fixes.length > 0 && (
            <FindingsBox kind="fix" title={TEXT.fixTitle} findings={summary.fixes}>
              {summary.moreFixes > 0 && <p className="note">{TEXT.morePoints(summary.moreFixes)}</p>}
            </FindingsBox>
          )}
          {summary.good.length > 0 && <FindingsBox kind="good" title={TEXT.goodTitle} findings={summary.good} />}
        </div>
      )}

      {groups.map(({ chunk, views: rowViews }) =>
        chunk ? (
          <div key={chunk.index} className="result-group" role="group" aria-label={`Chunk ${chunk.index + 1}: ${chunk.text}`}>
            <h3 className="result-group-title" lang="fr">
              <span className="tab-num" aria-hidden="true">
                {chunk.index + 1}
              </span>
              {chunk.text}
            </h3>
            {chipRow(rowViews)}
          </div>
        ) : (
          <div key="all">{chipRow(rowViews)}</div>
        ),
      )}

      <TrackLegend />
      <p className="note">
        Results come from an early model. Sounds linking to the next chunk, optional vowels and sounds next to nasal
        vowels can be marked wrongly.
      </p>
    </section>
  );
}

function FindingsBox({
  kind,
  title,
  findings,
  children,
}: {
  kind: "fix" | "good";
  title: string;
  findings: Finding[];
  children?: React.ReactNode;
}) {
  return (
    <div className={`box ${kind}`}>
      <h3>{title}</h3>
      <ul>
        {findings.map((finding, i) => (
          <li key={i}>
            <span className="mk" aria-hidden="true">
              {kind === "fix" ? "→" : "✓"}
            </span>
            <span>
              <FindingText finding={finding} />
            </span>
          </li>
        ))}
      </ul>
      {children}
    </div>
  );
}

function WordChip({
  view,
  open,
  cardId,
  onToggle,
  card,
}: {
  view: UnitView;
  open: boolean;
  cardId: string;
  onToggle: () => void;
  card: React.ReactNode;
}) {
  const badge =
    view.state === "ok" ? "✓" : view.state === "near" ? TEXT.closeBadge : TEXT.errors(view.problems.length);
  return (
    <>
      <button
        type="button"
        className={`wchip ${view.state}`}
        aria-expanded={open}
        aria-controls={open ? cardId : undefined}
        onClick={onToggle}
      >
        <span lang="fr">{view.label}</span>
        <span className="badge">{badge}</span>
      </button>
      {card}
    </>
  );
}

function WordCard({
  id,
  view,
  sentenceId,
  recording,
}: {
  id: string;
  view: UnitView;
  sentenceId: string;
  recording: Blob | null;
}) {
  const good = unitGood(view);
  const hints = hintsFor(view.result);
  return (
    <section className="wcard" id={id} aria-label={`Details: ${view.label}`}>
      <div className="wcard-head">
        <span className="eyebrow">
          <span lang="fr">{view.label}</span> · <span className="ipa">/{view.unit.ipa}/</span>
        </span>
        <span className="audio">
          <PlayButton src={audioUrl(sentenceId, "normal", { kind: "unit", unitId: view.unit.id })} label={TEXT.hearModel} />
          <HearYourself recording={recording} span={view.span} />
        </span>
      </div>
      <TrackChanges ops={view.result.ops} />
      <div className={`cols ${view.problems.length > 0 && good.length > 0 ? "" : "single"}`}>
        {view.problems.length > 0 && (
          <FindingsBox
            kind="fix"
            title={TEXT.fixTitle}
            findings={view.problems.map((problem) => ({ type: "fix", problem, label: "" }))}
          />
        )}
        {good.length > 0 && (
          <div className="box good">
            <h3>{TEXT.goodTitleInCard}</h3>
            <ul>
              {good.map((note, i) => (
                <li key={i}>
                  <span className="mk" aria-hidden="true">
                    ✓
                  </span>
                  <span>
                    <UnitGoodText note={note} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {hints.map((hint) => (
        <p key={hint} className="note hint">
          {hint}
        </p>
      ))}
    </section>
  );
}
