// Mirrors backend/api/schemas.py.

export type UnitType = "single" | "liaison_group" | "elision_group";
export type OpType = "match" | "substitution" | "insertion" | "deletion";

export interface Unit {
  id: string;
  type: UnitType;
  words: string[];
  phonemes: string[];
  ipa: string;
  liaison_consonant: string | null;
  scoring_focus: string;
}

export interface Chunk {
  index: number;
  text: string;
  units: Unit[];
}

export interface Sentence {
  sentence_id: string;
  text: string;
  chunks: Chunk[];
}

export interface Op {
  op_type: OpType;
  canonical_phoneme: string | null;
  decoded_phoneme: string | null;
  start_ms: number | null;
  end_ms: number | null;
  score: number | null;
}

export interface UnitResult {
  unit_id: string;
  score: number | null;
  feedback_text: string;
  ops: Op[];
}

export interface Attempt {
  sentence_id: string;
  chunk_index: number | null;
  unit_id: string | null;
  calibrated: boolean;
  results: UnitResult[];
}

export interface Health {
  status: "warming_up" | "ready" | "error";
  calibrated: boolean;
  detail: string | null;
}

export type Target = { kind: "chunk"; chunkIndex: number } | { kind: "unit"; unitId: string };
export type Speed = "normal" | "slow";
