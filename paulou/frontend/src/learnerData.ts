// Sounds that many learners find hard. A pedagogical ASSUMPTION carried over
// from the alignment-lab prototype (it was written for Vietnamese speakers
// learning French), not a measured list: replace it with data when there is
// any. Used only to word the "done well" notes (D63).
const N = "̃";

export const HARD_SOUNDS: ReadonlySet<string> = new Set(
  ["ʁ", "y", "ø", "œ", "ɔ" + N, "ɑ" + N, "ɛ" + N, "œ" + N, "ʒ", "ɥ"].map((s) => s.normalize("NFD")),
);

export const isHardSound = (phoneme: string) => HARD_SOUNDS.has(phoneme.normalize("NFD"));
