// All wording of the learner result view (Decision Log D63), in one place so a
// translation only touches this file. Sentences are built from the ops by
// templates, not written by the backend.

import type { ReactNode } from "react";
import type { Finding } from "./learnerModel";
import { unitGood } from "./learnerModel";
import type { Op } from "./types";

export function Ipa({ children }: { children: ReactNode }) {
  return <span className="ipa">/{children}/</span>;
}

const NEAR_REASONS: Record<string, string> = {
  missing_nasality: "missing nasality",
  extra_nasality: "extra nasality",
  not_rounded: "lips not rounded enough",
  over_rounded: "lips rounded too much",
  too_far_back: "tongue too far back",
  too_far_forward: "tongue too far forward",
  not_open_enough: "mouth not open enough",
  too_open: "mouth open too wide",
  missing_voicing: "missing voicing",
  extra_voicing: "extra voicing",
  wrong_place: "wrong place of articulation",
  wrong_manner: "wrong manner of articulation",
};

export const nearReasonText = (codes: string[]) => codes.map((c) => NEAR_REASONS[c] ?? c).join(", ");

export const TEXT = {
  fixTitle: "Needs fixing",
  goodTitle: "You did well",
  goodTitleInCard: "Already good",
  morePoints: (n: number) => `${n} more ${n === 1 ? "point" : "points"}, see them in each word.`,
  wordsCorrect: "words correct",
  soundsCorrect: "sounds correct",
  closeSounds: "close",
  hearModel: "Hear the model",
  hearYou: "Hear yourself",
  noOwnClip: "None of your sounds was found for this word",
  errors: (n: number) => `${n} ${n === 1 ? "error" : "errors"}`,
  closeBadge: "close",
  chipsLabel: "Words",
  trackLabel: "Sound by sound result",
};

const inWord = (label: string) => (label ? <> in <i>{label}</i></> : null);

/** The sentence for one mistake, e.g. "/ɔ̃/ in bonjour is close, heard as /o/: missing nasality". */
export function Describe({ op, after, label }: { op: Op; after: string | null; label: string }) {
  switch (op.kind) {
    case "S_near": {
      const why = nearReasonText(op.near_reasons);
      return (
        <>
          <Ipa>{op.canonical_phoneme}</Ipa>
          {inWord(label)} is close, heard as <Ipa>{op.decoded_phoneme}</Ipa>
          {why && <>: {why}</>}
        </>
      );
    }
    case "S":
      return (
        <>
          <Ipa>{op.canonical_phoneme}</Ipa>
          {inWord(label)} was heard as <Ipa>{op.decoded_phoneme}</Ipa>
        </>
      );
    case "D":
      return (
        <>
          missing <Ipa>{op.canonical_phoneme}</Ipa>
          {inWord(label)}
        </>
      );
    case "I":
      return after ? (
        <>
          extra <Ipa>{op.decoded_phoneme}</Ipa> after <Ipa>{after}</Ipa>
          {inWord(label)}
        </>
      ) : (
        <>
          extra <Ipa>{op.decoded_phoneme}</Ipa> at the start{inWord(label)}
        </>
      );
    default:
      return null;
  }
}

/** Plain-text version for accessible names. */
export function describePlain(op: Op): string {
  switch (op.kind) {
    case "M":
      return `${op.canonical_phoneme}: correct`;
    case "S_near": {
      const why = nearReasonText(op.near_reasons);
      return `${op.canonical_phoneme}: close, heard ${op.decoded_phoneme}${why ? `, ${why}` : ""}`;
    }
    case "S":
      return `${op.canonical_phoneme}: heard ${op.decoded_phoneme} instead`;
    case "D":
      return `${op.canonical_phoneme}: missing`;
    case "I":
      return `${op.decoded_phoneme}: extra sound`;
  }
}

export function FindingText({ finding }: { finding: Finding }) {
  switch (finding.type) {
    case "fix":
      return <Describe op={finding.problem.op} after={finding.problem.after} label={finding.label} />;
    case "hard":
      return (
        <>
          <Ipa>{finding.phoneme}</Ipa> in <i>{finding.label}</i> is correct
          {finding.first ? ", a sound many learners find hard" : " (hard sound)"}
        </>
      );
    case "allCorrect":
      return <>Everything is correct</>;
    case "wordsCorrect":
      return (
        <>
          {finding.labels.map((l, i) => (
            <span key={l}>
              {i > 0 && ", "}
              <i>{l}</i>
            </span>
          ))}{" "}
          correct
        </>
      );
    case "wordsCorrectCount":
      return <>{finding.count} words correct</>;
    case "near": {
      const why = nearReasonText(finding.op.near_reasons);
      return (
        <>
          <Ipa>{finding.op.canonical_phoneme}</Ipa> in <i>{finding.label}</i> was already close{why && <>, only {why}</>}
        </>
      );
    }
    case "soundsCorrect":
      return (
        <>
          {finding.correct} of {finding.total} sounds correct
        </>
      );
  }
}

export function UnitGoodText({ note }: { note: ReturnType<typeof unitGood>[number] }) {
  switch (note.type) {
    case "allCorrect":
      return <>The whole word is correct</>;
    case "hard":
      return (
        <>
          <Ipa>{note.phoneme}</Ipa> is correct, a sound many learners find hard
        </>
      );
    case "correct":
      return (
        <>
          Correct:{" "}
          {note.phonemes.map((p, i) => (
            <span key={p}>
              {i > 0 && ", "}
              <Ipa>{p}</Ipa>
            </span>
          ))}
        </>
      );
  }
}

