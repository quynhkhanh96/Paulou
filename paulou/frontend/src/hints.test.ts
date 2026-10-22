import { hintsFor } from "./hints";
import { op } from "./fixtures";
import type { UnitResult } from "./types";

const result = (ops: UnitResult["ops"]): UnitResult => ({ unit_id: "u", score: null, feedback_text: "", ops });

describe("hintsFor", () => {
  it("is empty for a clean result", () => {
    expect(hintsFor(result([op("match", "a", "a")]))).toEqual([]);
  });

  it("explains extra sounds as a possible cross-chunk liaison (D51)", () => {
    const [hint] = hintsFor(result([op("match", "a", "a"), op("insertion", null, "z")]));
    expect(hint).toMatch(/liaison/i);
  });

  it("explains a dropped schwa (D50 finding)", () => {
    const hints = hintsFor(result([op("deletion", "ə", null)]));
    expect(hints).toHaveLength(1);
    expect(hints[0]).toMatch(/schwa/i);
  });

  it("does not mention the schwa for other deletions", () => {
    expect(hintsFor(result([op("deletion", "z", null)]))).toEqual([]);
  });

  it("warns about an insertion right after a nasal vowel (D47)", () => {
    const hints = hintsFor(result([op("match", "ɔ̃", "ɔ̃"), op("insertion", null, "n")]));
    expect(hints.some((h) => /nasal vowel/i.test(h))).toBe(true);
  });

  it("does not give the nasal warning when the insertion follows an oral vowel", () => {
    const hints = hintsFor(result([op("match", "a", "a"), op("insertion", null, "n")]));
    expect(hints.some((h) => /nasal vowel/i.test(h))).toBe(false);
  });
});
