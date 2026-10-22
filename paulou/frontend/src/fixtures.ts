import type { Attempt, Op, Sentence } from "./types";

export const SENTENCE: Sentence = {
  sentence_id: "abc123",
  text: "Bonjour les amis",
  chunks: [
    {
      index: 0,
      text: "Bonjour",
      units: [
        { id: "c0_unit_0", type: "single", words: ["Bonjour"], phonemes: ["b", "ɔ̃", "ʒ", "u", "ʁ"], ipa: "bɔ̃ʒuʁ", liaison_consonant: null, scoring_focus: "phoneme_accuracy" },
      ],
    },
    {
      index: 1,
      text: "les amis",
      units: [
        { id: "c1_unit_0", type: "liaison_group", words: ["les", "amis"], phonemes: ["l", "e", "z", "a", "m", "i"], ipa: "lezami", liaison_consonant: "z", scoring_focus: "liaison_presence_and_continuity" },
      ],
    },
  ],
};

export const op = (op_type: Op["op_type"], canonical: string | null, decoded: string | null): Op => ({
  op_type,
  canonical_phoneme: canonical,
  decoded_phoneme: decoded,
  start_ms: op_type === "deletion" ? null : 0,
  end_ms: op_type === "deletion" ? null : 50,
  score: null,
});

export const ATTEMPT: Attempt = {
  sentence_id: "abc123",
  chunk_index: 1,
  unit_id: null,
  calibrated: false,
  results: [
    {
      unit_id: "c1_unit_0",
      score: null,
      feedback_text: "Overall: good effort. Missing the z sound.",
      ops: [op("match", "l", "l"), op("match", "e", "e"), op("deletion", "z", null), op("substitution", "a", "ɑ"), op("insertion", null, "t")],
    },
  ],
};
