import type { Op, OpType } from "./types";

// Canonical view (Decision Log D37, view 1): the expected sounds in order, each
// marked by what happened to it. Shape and wording carry the meaning, colour
// only reinforces it. An insertion sits between the ops it follows, because
// `ops` arrive in canonical order.

const META: Record<OpType, { glyph: string; label: string; css: string }> = {
  match: { glyph: "✓", label: "said correctly", css: "match" },
  substitution: { glyph: "≠", label: "said as another sound", css: "substitution" },
  insertion: { glyph: "+", label: "extra sound", css: "insertion" },
  deletion: { glyph: "–", label: "missing", css: "deletion" },
};

export function describeOp(op: Op): string {
  switch (op.op_type) {
    case "match":
      return `${op.canonical_phoneme}: ${META.match.label}`;
    case "substitution":
      return `${op.canonical_phoneme}: heard ${op.decoded_phoneme} instead`;
    case "insertion":
      return `${op.decoded_phoneme}: ${META.insertion.label}`;
    case "deletion":
      return `${op.canonical_phoneme}: ${META.deletion.label}`;
  }
}

export function PhonemeStrip({ ops }: { ops: Op[] }) {
  return (
    <ol className="strip" aria-label="Sound by sound result">
      {ops.map((op, i) => {
        const meta = META[op.op_type];
        const main = op.op_type === "insertion" ? op.decoded_phoneme : op.canonical_phoneme;
        return (
          <li key={i} className={`phone ${meta.css}`} aria-label={describeOp(op)}>
            <span className="phone-glyph" aria-hidden="true">
              {meta.glyph}
            </span>
            <span className="phone-sound" aria-hidden="true">
              {main}
            </span>
            {op.op_type === "substitution" && (
              <span className="phone-heard" aria-hidden="true">
                heard {op.decoded_phoneme}
              </span>
            )}
            {op.op_type === "insertion" && (
              <span className="phone-heard" aria-hidden="true">
                extra
              </span>
            )}
            {op.op_type === "deletion" && (
              <span className="phone-heard" aria-hidden="true">
                missing
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function Legend() {
  return (
    <ul className="legend" aria-label="Legend">
      {(Object.keys(META) as OpType[]).map((type) => (
        <li key={type} className={`legend-item ${META[type].css}`}>
          <span aria-hidden="true">{META[type].glyph}</span> {META[type].label}
        </li>
      ))}
    </ul>
  );
}
