import { describePlain, TEXT } from "./learnerText";
import type { Op } from "./types";

// Track-changes view of one unit (Decision Log D63): the expected sounds stay
// as the spine; each kind of mistake has its own colour AND shape, so colour is
// never the only cue:
//   close substitution  yellow highlight on the lower half, the heard sound above
//   far substitution    red-orange highlight, wavy underline, the heard sound above
//   missing             dashed purple frame, struck through
//   extra               blue pill "+x" over a ‸ caret between two sounds
//   correct             teal text

type Token =
  | { kind: "single"; op: Op }
  | { kind: "extra"; ops: Op[] };

// Consecutive insertions share one caret: "+ab".
function tokens(ops: Op[]): Token[] {
  const out: Token[] = [];
  for (const op of ops) {
    const last = out[out.length - 1];
    if (op.kind === "I" && last?.kind === "extra") last.ops.push(op);
    else if (op.kind === "I") out.push({ kind: "extra", ops: [op] });
    else out.push({ kind: "single", op });
  }
  return out;
}

export function TrackChanges({ ops }: { ops: Op[] }) {
  return (
    <ol className="track" aria-label={TEXT.trackLabel}>
      {tokens(ops).map((token, i) => {
        if (token.kind === "extra") {
          const heard = token.ops.map((o) => o.decoded_phoneme).join(" ");
          return (
            <li key={i} className="tk tk-I" aria-label={`${heard}: extra sound`}>
              <span className="tk-top" aria-hidden="true">
                +{heard}
              </span>
              <span className="tk-main" aria-hidden="true">
                ‸
              </span>
            </li>
          );
        }
        const { op } = token;
        const heard = op.kind === "S" || op.kind === "S_near" ? op.decoded_phoneme : null;
        return (
          <li key={i} className={`tk tk-${op.kind}`} aria-label={describePlain(op)}>
            <span className="tk-top" aria-hidden="true">
              {heard}
            </span>
            <span className="tk-main" aria-hidden="true">
              {op.canonical_phoneme}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function TrackLegend() {
  return (
    <ul className="track-legend" aria-label="Legend">
      <li>
        <span className="tk tk-M" aria-hidden="true">
          <span className="tk-main">a</span>
        </span>{" "}
        correct
      </li>
      <li>
        <span className="tk tk-S_near" aria-hidden="true">
          <span className="tk-main">a</span>
        </span>{" "}
        close
      </li>
      <li>
        <span className="tk tk-S" aria-hidden="true">
          <span className="tk-main">a</span>
        </span>{" "}
        replaced
      </li>
      <li>
        <span className="tk tk-D" aria-hidden="true">
          <span className="tk-main">a</span>
        </span>{" "}
        missing
      </li>
      <li>
        <span className="tk tk-I" aria-hidden="true">
          <span className="tk-top">+a</span>
        </span>{" "}
        extra
      </li>
    </ul>
  );
}
