from stages.chunk_analyzer.elision.elision import detect_elision


def test_recognized_clitics():
    assert detect_elision("l'") == ["l"]
    assert detect_elision("d'") == ["d"]
    assert detect_elision("j'") == ["ʒ"]
    assert detect_elision("m'") == ["m"]
    assert detect_elision("n'") == ["n"]
    assert detect_elision("qu'") == ["k"]
    assert detect_elision("s'") == ["s"]
    assert detect_elision("t'") == ["t"]
    assert detect_elision("c'") == ["s"]


def test_case_insensitive():
    assert detect_elision("L'") == ["l"]
    assert detect_elision("Qu'") == ["k"]


def test_ordinary_word_returns_none():
    assert detect_elision("amis") is None
    assert detect_elision("le") is None  # non-elided form — not in the closed list


def test_word_kept_whole_by_tokenizer_returns_none():
    # "aujourd'hui" is NOT split by spaCy's tokenizer (verified empirically)
    # and contains an apostrophe but isn't itself an elided clitic.
    assert detect_elision("aujourd'hui") is None


def test_typographic_apostrophe_does_not_match():
    # Only the straight ASCII apostrophe (U+0027) is recognized — matches
    # what spaCy's French tokenizer actually produces (verified empirically).
    assert detect_elision("l\u2019") is None  # U+2019 RIGHT SINGLE QUOTATION MARK
