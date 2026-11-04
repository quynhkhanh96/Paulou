import { buildUnitViews, firstToOpen, summarize, unitGood } from "./learnerModel";
import type { Op, OpKind, Sentence, Unit, UnitResult } from "./types";

const N = "̃";
const KIND_TYPE = { M: "match", S_near: "substitution", S: "substitution", D: "deletion", I: "insertion" } as const;

const op = (kind: OpKind, canonical: string | null, decoded: string | null, near: string[] = [], at = 0): Op => ({
  op_type: KIND_TYPE[kind],
  kind,
  near_reasons: near,
  canonical_phoneme: canonical,
  decoded_phoneme: decoded,
  start_ms: kind === "D" ? null : at,
  end_ms: kind === "D" ? null : at + 50,
  score: null,
});
const result = (unit_id: string, ops: Op[]): UnitResult => ({ unit_id, score: null, feedback_text: "", ops });
const unit = (id: string, word: string, phonemes: string[]): Unit => ({
  id,
  type: "single",
  words: [word],
  phonemes,
  ipa: phonemes.join(""),
  liaison_consonant: null,
  scoring_focus: "",
});

const SENTENCE: Sentence = {
  sentence_id: "s",
  text: "bonjour les amis",
  chunks: [
    { index: 0, text: "bonjour", units: [unit("c0_unit_0", "bonjour", ["b", "ɔ" + N, "ʒ", "u", "ʁ"])] },
    { index: 1, text: "les amis", units: [unit("c1_unit_0", "les", ["l", "e"]), unit("c1_unit_1", "amis", ["a", "m", "i"])] },
  ],
};

const bonjour = result("c0_unit_0", [
  op("M", "b", "b"),
  op("S_near", "ɔ" + N, "o", ["missing_nasality"], 50),
  op("M", "ʒ", "ʒ", [], 100),
  op("I", null, "ə", [], 150),
  op("M", "u", "u", [], 200),
  op("D", "ʁ", null),
]);
const les = result("c1_unit_0", [op("M", "l", "l"), op("M", "e", "e")]);
const amis = result("c1_unit_1", [op("M", "a", "a"), op("S", "m", "n", [], 60), op("M", "i", "i")]);

describe("buildUnitViews", () => {
  const views = buildUnitViews(SENTENCE, [amis, bonjour, les]);

  it("follows the order of the sentence, not of the results", () => {
    expect(views.map((v) => v.unit.id)).toEqual(["c0_unit_0", "c1_unit_0", "c1_unit_1"]);
    expect(views.map((v) => v.chunkIndex)).toEqual([0, 1, 1]);
  });

  it("classifies each unit: ok, near (only close mistakes) or err", () => {
    const only = (r: UnitResult) => buildUnitViews(SENTENCE, [r])[0].state;
    expect(only(les)).toBe("ok");
    expect(only(result("c0_unit_0", [op("M", "b", "b"), op("S_near", "z", "s", ["missing_voicing"])]))).toBe("near");
    expect(only(bonjour)).toBe("err");
    expect(only(amis)).toBe("err");
  });

  it("remembers the sound before each mistake, within its unit", () => {
    const problems = views[0].problems;
    expect(problems.map((p) => [p.op.kind, p.after])).toEqual([
      ["S_near", "b"],
      ["I", "ʒ"],
      ["D", "u"],
    ]);
  });

  it("splits the correct sounds into hard and other, without duplicates", () => {
    expect(views[0].hardCorrect).toEqual(["ʒ"]);
    expect(views[0].otherCorrect).toEqual(["b", "u"]);
  });

  it("measures the span of the learner's voice, null when only deletions", () => {
    expect(views[0].span).toEqual({ startMs: 0, endMs: 250 });
    expect(buildUnitViews(SENTENCE, [result("c0_unit_0", [op("D", "b", null)])])[0].span).toBeNull();
  });

  it("ignores results for units the sentence does not have", () => {
    expect(buildUnitViews(SENTENCE, [result("zzz", [op("M", "a", "a")])])).toEqual([]);
  });
});

describe("summarize", () => {
  const views = buildUnitViews(SENTENCE, [bonjour, les, amis]);
  const s = summarize(views);

  it("counts words, sounds and close sounds", () => {
    expect([s.wordsOk, s.wordsTotal]).toEqual([1, 3]);
    expect([s.soundsOk, s.soundsTotal]).toEqual([7, 10]); // 10 expected sounds (5 + 2 + 3), the insertion is not one of them
    expect(s.near).toBe(1);
  });

  it("lists at most two fixes, far mistakes before close ones", () => {
    expect(s.fixes).toHaveLength(2);
    const kinds = s.fixes.map((f) => (f.type === "fix" ? f.problem.op.kind : null));
    expect(kinds).toEqual(["I", "D"]); // the close substitution (first in the sentence) comes after them
    expect(s.moreFixes).toBe(2); // 4 problems in total: S_near, I, D, S
  });

  it("puts a far substitution ahead of a close one even when it comes later", () => {
    const only = summarize(buildUnitViews(SENTENCE, [result("c0_unit_0", [op("S_near", "z", "s", ["missing_voicing"]), op("S", "m", "n")])]));
    expect(only.fixes.map((f) => (f.type === "fix" ? f.problem.op.kind : null))).toEqual(["S", "S_near"]);
  });

  it("praises concrete things: a hard sound that was right, then whole words", () => {
    expect(s.good.map((g) => g.type)).toEqual(["hard", "wordsCorrect"]);
    expect(s.good[0]).toMatchObject({ type: "hard", phoneme: "ʒ", label: "bonjour", first: true });
    expect(s.good[1]).toEqual({ type: "wordsCorrect", labels: ["les"] });
  });

  it("says so when everything is right", () => {
    const all = summarize(buildUnitViews(SENTENCE, [result("c0_unit_0", [op("M", "b", "b")]), les, result("c1_unit_1", [op("M", "a", "a")])]));
    expect(all.fixes).toEqual([]);
    expect(all.good[0]).toEqual({ type: "allCorrect" });
    expect(all.wordsOk).toBe(all.wordsTotal);
  });

  it("falls back to close sounds, then to a plain count", () => {
    const nearOnly = summarize(buildUnitViews(SENTENCE, [result("c0_unit_0", [op("S_near", "z", "s", ["missing_voicing"]), op("D", "b", null)])]));
    expect(nearOnly.good[0]).toMatchObject({ type: "near", label: "bonjour" });
    const count = summarize(buildUnitViews(SENTENCE, [result("c0_unit_0", [op("M", "b", "b"), op("D", "a", null)])]));
    expect(count.good).toEqual([{ type: "soundsCorrect", correct: 1, total: 2 }]);
  });

  it("has nothing to praise when nothing was right", () => {
    const none = summarize(buildUnitViews(SENTENCE, [result("c0_unit_0", [op("D", "b", null)])]));
    expect(none.good).toEqual([]);
  });
});

describe("unitGood and firstToOpen", () => {
  it("lists what was good inside one unit", () => {
    const [view] = buildUnitViews(SENTENCE, [bonjour]);
    expect(unitGood(view)).toEqual([
      { type: "hard", phoneme: "ʒ" },
      { type: "correct", phonemes: ["b", "u"] },
    ]);
    const [ok] = buildUnitViews(SENTENCE, [les]);
    expect(unitGood(ok)[0]).toEqual({ type: "allCorrect" });
  });

  it("opens the first unit that needs work", () => {
    expect(firstToOpen(buildUnitViews(SENTENCE, [les, bonjour, amis]))).toBe("c0_unit_0");
    expect(firstToOpen(buildUnitViews(SENTENCE, [les]))).toBeNull();
  });
});
