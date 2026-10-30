// Pure functions behind the learner result view (Decision Log D63): they take
// the sentence and the ops the API returned and compute what to show. No
// alignment here (the backend did it, D38) and no wording (learnerText.tsx).

import { isHardSound } from "./learnerData";
import type { Op, Sentence, Unit, UnitResult } from "./types";

export type UnitState = "ok" | "near" | "err";

/** One op that is not a match, with the sound that came before it in the unit. */
export interface Problem {
  op: Op;
  /** Previous expected sound in the same unit; null at the start of the unit. */
  after: string | null;
}

export interface UnitView {
  unit: Unit;
  chunkIndex: number;
  result: UnitResult;
  label: string;
  state: UnitState;
  problems: Problem[];
  /** Distinct correct sounds, split into the hard ones and the rest. */
  hardCorrect: string[];
  otherCorrect: string[];
  /** Span of the learner's own voice for this unit, null when nothing was heard. */
  span: { startMs: number; endMs: number } | null;
}

export type Finding =
  | { type: "fix"; problem: Problem; label: string }
  | { type: "hard"; phoneme: string; label: string; first: boolean }
  | { type: "allCorrect" }
  | { type: "wordsCorrect"; labels: string[] }
  | { type: "wordsCorrectCount"; count: number }
  | { type: "near"; op: Op; label: string }
  | { type: "soundsCorrect"; correct: number; total: number };

export interface Summary {
  wordsOk: number;
  wordsTotal: number;
  soundsOk: number;
  soundsTotal: number;
  near: number;
  fixes: Finding[];
  moreFixes: number;
  good: Finding[];
}

const MAX_PER_BOX = 2;
const MAX_HARD_NOTES = 3;
const MAX_WORD_NAMES = 3;

export const unitLabel = (unit: Unit) => unit.words.join(" ");

function viewOf(unit: Unit, chunkIndex: number, result: UnitResult): UnitView {
  const problems: Problem[] = [];
  const hard = new Set<string>();
  const other = new Set<string>();
  let after: string | null = null;
  for (const op of result.ops) {
    if (op.kind === "M" && op.canonical_phoneme) {
      (isHardSound(op.canonical_phoneme) ? hard : other).add(op.canonical_phoneme);
    } else if (op.kind !== "M") {
      problems.push({ op, after });
    }
    if (op.canonical_phoneme) after = op.canonical_phoneme;
  }
  const state: UnitState = problems.length === 0 ? "ok" : problems.every((p) => p.op.kind === "S_near") ? "near" : "err";

  const times = result.ops.filter((op) => op.start_ms !== null && op.end_ms !== null);
  const span = times.length
    ? {
        startMs: Math.min(...times.map((op) => op.start_ms as number)),
        endMs: Math.max(...times.map((op) => op.end_ms as number)),
      }
    : null;

  return {
    unit,
    chunkIndex,
    result,
    label: unitLabel(unit),
    state,
    problems,
    hardCorrect: [...hard],
    otherCorrect: [...other],
    span,
  };
}

/** One view per scored unit, in sentence order. Results for units the sentence
 *  does not contain are ignored. */
export function buildUnitViews(sentence: Sentence, results: UnitResult[]): UnitView[] {
  const byId = new Map(results.map((r) => [r.unit_id, r]));
  const views: UnitView[] = [];
  for (const chunk of sentence.chunks) {
    for (const unit of chunk.units) {
      const result = byId.get(unit.id);
      if (result) views.push(viewOf(unit, chunk.index, result));
    }
  }
  return views;
}

/** Far mistakes before close ones; otherwise keep the order of the sentence. */
const farFirst = (a: Problem, b: Problem) => Number(a.op.kind === "S_near") - Number(b.op.kind === "S_near");

export function summarize(views: UnitView[]): Summary {
  const allOps = views.flatMap((v) => v.result.ops);
  const soundsTotal = allOps.filter((op) => op.canonical_phoneme !== null).length;
  const soundsOk = allOps.filter((op) => op.kind === "M").length;
  const near = allOps.filter((op) => op.kind === "S_near").length;
  const wordsOk = views.filter((v) => v.state === "ok").length;

  // Needs fixing: at most two, far mistakes first.
  const problems = views.flatMap((v) => v.problems.map((problem) => ({ problem, label: v.label })));
  problems.sort((a, b) => farFirst(a.problem, b.problem));
  const fixes: Finding[] = problems.slice(0, MAX_PER_BOX).map(({ problem, label }) => ({ type: "fix", problem, label }));

  // Done well: concrete things, at most two (hard sounds can add a third).
  const good: Finding[] = [];
  const hardSeen = new Set<string>();
  for (const v of views) {
    for (const op of v.result.ops) {
      if (good.length >= MAX_HARD_NOTES) break;
      if (op.kind !== "M" || !op.canonical_phoneme || !isHardSound(op.canonical_phoneme)) continue;
      const key = op.canonical_phoneme.normalize("NFD");
      if (hardSeen.has(key)) continue;
      good.push({ type: "hard", phoneme: op.canonical_phoneme, label: v.label, first: hardSeen.size === 0 });
      hardSeen.add(key);
    }
  }
  if (good.length < 2 && wordsOk > 0) {
    const labels = views.filter((v) => v.state === "ok").map((v) => v.label);
    if (wordsOk === views.length) good.unshift({ type: "allCorrect" });
    else if (labels.length <= MAX_WORD_NAMES) good.push({ type: "wordsCorrect", labels });
    else good.push({ type: "wordsCorrectCount", count: wordsOk });
  }
  if (good.length < 2) {
    const seen = new Set<string>();
    for (const v of views) {
      for (const op of v.result.ops) {
        const key = `${op.canonical_phoneme}>${op.decoded_phoneme}`;
        if (good.length >= 2) break;
        if (op.kind !== "S_near" || seen.has(key)) continue;
        seen.add(key);
        good.push({ type: "near", op, label: v.label });
      }
    }
  }
  if (good.length === 0 && soundsOk > 0) good.push({ type: "soundsCorrect", correct: soundsOk, total: soundsTotal });

  return {
    wordsOk,
    wordsTotal: views.length,
    soundsOk,
    soundsTotal,
    near,
    fixes,
    moreFixes: Math.max(0, problems.length - MAX_PER_BOX),
    good,
  };
}

/** The "done well" notes inside one unit's card. */
export function unitGood(view: UnitView): ({ type: "allCorrect" } | { type: "hard"; phoneme: string } | { type: "correct"; phonemes: string[] })[] {
  const notes: ReturnType<typeof unitGood> = [];
  if (view.state === "ok") notes.push({ type: "allCorrect" });
  for (const phoneme of view.hardCorrect) notes.push({ type: "hard", phoneme });
  if (view.otherCorrect.length) notes.push({ type: "correct", phonemes: view.otherCorrect });
  return notes;
}

/** The first unit that needs work, or null when everything was right. */
export function firstToOpen(views: UnitView[]): string | null {
  return views.find((v) => v.state !== "ok")?.unit.id ?? null;
}
