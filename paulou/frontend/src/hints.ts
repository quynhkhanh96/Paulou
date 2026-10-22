import type { UnitResult } from "./types";

// Known limits of the MVP (Decision Log D47, D51, schwa finding in the
// Roadmap). Shown next to a result when the pattern that causes them appears,
// so a learner does not read a model limitation as their own mistake.
export function hintsFor(result: UnitResult): string[] {
  const hints: string[] = [];
  const hasInsertion = result.ops.some((op) => op.op_type === "insertion");
  if (hasInsertion) {
    hints.push(
      "An extra sound can be a real liaison that links this word to the next chunk. The app does not model links across chunks yet.",
    );
  }
  if (result.ops.some((op) => op.op_type === "deletion" && op.canonical_phoneme === "ə")) {
    hints.push(
      "Dropping the schwa (ə) is normal in everyday speech. The app still counts it as missing.",
    );
  }
  const nasalVowel = (phoneme: string | null) => !!phoneme && phoneme.normalize("NFD").includes("̃");
  const nasalThenInsertion = result.ops.some(
    (op, i) => op.op_type === "insertion" && i > 0 && nasalVowel(result.ops[i - 1].canonical_phoneme),
  );
  if (nasalThenInsertion) {
    hints.push("The model sometimes hears an extra consonant after a nasal vowel that was not spoken.");
  }
  return hints;
}
