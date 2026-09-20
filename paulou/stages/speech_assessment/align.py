"""Alignment: 3-way Levenshtein (substitution + insertion + deletion)
between a canonical phoneme sequence and a free-phone-recognizer's decoded
output for the same audio span.

Pure, deterministic logic — no Protocol/registry wrapper (Decision Log D12).

Replaces the old DEL/INS-only alignment (Architecture Spec stage 5c,
originally scoped for Branch 2 only) under Decision Log D36's single
free-decode + 3-way alignment pipeline. Also replaces D20's count-based
phoneme-to-unit grouping: since insertions/deletions can make the
canonical and decoded sequences different lengths, there's no reliable way
to recover unit membership by counting after the fact. Instead, unit
membership is assigned DURING alignment, from a `unit_ids` array kept
parallel to `canonical_phonemes` (index i of both refers to the same
phoneme) — one array position consumed per canonical phoneme, exactly
like the phonemes themselves.

Standard Levenshtein DP with equal weights (sub_cost = del_cost =
ins_cost = 1) — deliberately not tuned per error type. A useful emergent
property of equal weights: a single real mispronunciation is always
resolved as ONE substitution (cost 1) rather than a deletion+insertion
pair (cost 2) for the same event, so the DP naturally prefers the more
useful pedagogical reading without any special-casing.

Backtrace tie-breaking (needed because equal weights create ties often):
diagonal (match or substitution) is preferred over deletion, which is
preferred over insertion. This is a deliberate, documented choice — not
an arbitrary implementation detail — because it makes the output
deterministic (required for exact-match unit tests) and because reading a
frame as "a phone was actually produced there" (match/substitution) is a
more natural interpretation of the same acoustic evidence than "the
expected phone vanished and an unrelated one appeared from nowhere."

insertion attribution: an insertion has no canonical counterpart, so it
can't inherit a unit_id from the position it consumes (it doesn't consume
one). By convention (product decision, not a technical constraint), it
attaches to the PRECEDING unit — the last unit_id seen so far in the
(forward-order) op sequence. An insertion with nothing preceding it (the
very start of the chunk) attaches to the first unit instead.
"""

from core.models import AlignmentOp, AlignmentOpType


def align_phonemes(
    canonical_phonemes: list[str],
    unit_ids: list[str],
    decoded_phonemes: list[str],
    decoded_confidences: list[float],
    decoded_boundaries: list[tuple[int, int]],
) -> list[AlignmentOp]:
    """Align `canonical_phonemes` against `decoded_phonemes`, returning one
    AlignmentOp per operation in the optimal edit path (in canonical order).

    `unit_ids[i]` must be the PronunciationUnit id that owns
    `canonical_phonemes[i]`, for every i — same length as
    `canonical_phonemes`. `decoded_confidences[j]` and
    `decoded_boundaries[j]` must correspond to `decoded_phonemes[j]`, for
    every j — same length as `decoded_phonemes`.

    Raises ValueError if `canonical_phonemes` is empty (nothing to align
    against — a chunk with no phonemes is malformed) or if any of the
    three "parallel to decoded_phonemes" lists have a different length
    from it, or `unit_ids` has a different length from `canonical_phonemes`.
    """
    if not canonical_phonemes:
        raise ValueError("canonical_phonemes must not be empty.")
    if len(unit_ids) != len(canonical_phonemes):
        raise ValueError(
            f"unit_ids has {len(unit_ids)} entries but canonical_phonemes "
            f"has {len(canonical_phonemes)}."
        )
    if not (len(decoded_confidences) == len(decoded_boundaries) == len(decoded_phonemes)):
        raise ValueError(
            "decoded_phonemes, decoded_confidences, and decoded_boundaries "
            f"must have the same length (got {len(decoded_phonemes)}, "
            f"{len(decoded_confidences)}, {len(decoded_boundaries)})."
        )

    n = len(canonical_phonemes)
    m = len(decoded_phonemes)

    # --- DP cost table ---
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag_cost = 0 if canonical_phonemes[i - 1] == decoded_phonemes[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + diag_cost,  # match or substitution
                dp[i - 1][j] + 1,  # deletion
                dp[i][j - 1] + 1,  # insertion
            )

    # --- Backtrace from (n, m) to (0, 0) ---
    # Each entry: (op_type, canonical_index_or_None, decoded_index_or_None)
    trace: list[tuple[AlignmentOpType, int | None, int | None]] = []
    i, j = n, m
    while (i, j) != (0, 0):
        if i > 0 and j > 0:
            diag_cost = 0 if canonical_phonemes[i - 1] == decoded_phonemes[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + diag_cost:
                op_type: AlignmentOpType = "match" if diag_cost == 0 else "substitution"
                trace.append((op_type, i - 1, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            trace.append(("deletion", i - 1, None))
            i -= 1
            continue
        # j must be > 0 here — the only remaining option.
        trace.append(("insertion", None, j - 1))
        j -= 1

    trace.reverse()  # now in canonical (forward) order

    # --- Build AlignmentOps, resolving insertion unit_id attribution ---
    ops: list[AlignmentOp] = []
    last_unit_id = unit_ids[0]  # fallback for an insertion before anything else
    for op_type, c_idx, d_idx in trace:
        if op_type == "deletion":
            unit_id = unit_ids[c_idx]
            last_unit_id = unit_id
            ops.append(
                AlignmentOp(
                    op_type="deletion",
                    unit_id=unit_id,
                    canonical_phoneme=canonical_phonemes[c_idx],
                    decoded_phoneme=None,
                    confidence=None,
                    start_ms=None,
                    end_ms=None,
                )
            )
        elif op_type == "insertion":
            start_ms, end_ms = decoded_boundaries[d_idx]
            ops.append(
                AlignmentOp(
                    op_type="insertion",
                    unit_id=last_unit_id,
                    canonical_phoneme=None,
                    decoded_phoneme=decoded_phonemes[d_idx],
                    confidence=decoded_confidences[d_idx],
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
        else:  # match or substitution
            unit_id = unit_ids[c_idx]
            last_unit_id = unit_id
            start_ms, end_ms = decoded_boundaries[d_idx]
            ops.append(
                AlignmentOp(
                    op_type=op_type,
                    unit_id=unit_id,
                    canonical_phoneme=canonical_phonemes[c_idx],
                    decoded_phoneme=decoded_phonemes[d_idx],
                    confidence=decoded_confidences[d_idx],
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )

    return ops