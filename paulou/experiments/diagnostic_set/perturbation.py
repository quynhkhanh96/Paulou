"""Apply a DiagnosticCase's perturbation to its native phoneme sequence.

Pure function — no Protocol/registry (same reasoning as the liaison rule
engine, D12): there is no swappable "perturbation implementation", this is
plain data transformation. Kept as its own module so it can be sanity-
checked without loading Piper or any model (see the __main__ block).
"""

from experiments.diagnostic_set.cases import DiagnosticCase


def apply_perturbation(case: DiagnosticCase) -> list[str]:
    """Return the PERTURBED phoneme list for a case (native list unchanged).

    - native: returns a copy of canonical_phonemes, unchanged.
    - deletion: removes canonical_phonemes[target_index].
    - substitution: replaces canonical_phonemes[target_index] with
      injected_phoneme.
    - insertion: inserts injected_phoneme at target_index (i.e. before the
      phoneme currently at that index; inserting at len(list) appends).
    """
    phonemes = list(case.canonical_phonemes)

    if case.perturbation_type == "native":
        return phonemes

    if case.target_index is None:
        raise ValueError(
            f"{case.case_id}: target_index is required for "
            f"perturbation_type={case.perturbation_type!r}"
        )

    if case.perturbation_type == "deletion":
        del phonemes[case.target_index]
        return phonemes

    if case.perturbation_type == "substitution":
        if case.injected_phoneme is None:
            raise ValueError(f"{case.case_id}: substitution needs injected_phoneme")
        phonemes[case.target_index] = case.injected_phoneme
        return phonemes

    if case.perturbation_type == "insertion":
        if case.injected_phoneme is None:
            raise ValueError(f"{case.case_id}: insertion needs injected_phoneme")
        phonemes.insert(case.target_index, case.injected_phoneme)
        return phonemes

    raise ValueError(f"{case.case_id}: unknown perturbation_type "
                      f"{case.perturbation_type!r}")


if __name__ == "__main__":
    from experiments.diagnostic_set.cases import build_cases

    for case in build_cases():
        perturbed = apply_perturbation(case)
        print(f"{case.case_id}:")
        print(f"  native:    {case.canonical_phonemes}")
        print(f"  perturbed: {perturbed}")
