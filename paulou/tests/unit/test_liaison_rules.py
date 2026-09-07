from stages.liaison.rule_engine import apply_liaison_rules, get_liaison_consonant


def test_obligatoire_determiner_noun():
    result = apply_liaison_rules([("les", "DET"), ("amis", "NOUN")])
    assert result[0].applies is True
    assert result[0].consonant == "z"
    assert result[0].rule_type == "obligatoire"


def test_interdite_before_h_aspire():
    result = apply_liaison_rules([("les", "DET"), ("héros", "NOUN")])
    assert result[0].applies is False
    assert result[0].consonant is None
    assert result[0].rule_type == "interdite"


def test_interdite_after_et():
    result = apply_liaison_rules([("et", "CCONJ"), ("alors", "ADV")])
    assert result[0].applies is False
    assert result[0].rule_type == "interdite"


def test_interdite_subject_noun_before_verb():
    # Simplified rule (no number agreement available from POS alone) —
    # see docstring of _is_interdite_by_grammar.
    result = apply_liaison_rules([("enfant", "NOUN"), ("arrive", "VERB")])
    assert result[0].applies is False
    assert result[0].rule_type == "interdite"


def test_facultative_not_predicted():
    # "pas encore" — classic facultative case, not covered by any
    # obligatoire or interdite pattern.
    result = apply_liaison_rules([("pas", "ADV"), ("encore", "ADV")])
    assert result[0].rule_type == "facultative"
    assert result[0].applies is False


def test_no_liaison_before_consonant_initial_word():
    result = apply_liaison_rules([("les", "DET"), ("chats", "NOUN")])
    assert result[0].applies is False
    assert result[0].consonant is None
    assert result[0].rule_type == "interdite"


def test_no_liaison_when_word_has_no_liaison_consonant():
    # "amie" ends in a vowel — nothing to liaise regardless of what follows.
    result = apply_liaison_rules([("amie", "NOUN"), ("adorable", "ADJ")])
    assert result[0].applies is False
    assert result[0].consonant is None
    assert result[0].rule_type == "interdite"


def test_pronoun_clitic_before_verb():
    result = apply_liaison_rules([("nous", "PRON"), ("avons", "VERB")])
    assert result[0].applies is True
    assert result[0].consonant == "z"
    assert result[0].rule_type == "obligatoire"


def test_adjective_before_noun():
    result = apply_liaison_rules([("petit", "ADJ"), ("ami", "NOUN")])
    assert result[0].applies is True
    assert result[0].consonant == "t"


def test_monosyllabic_preposition():
    result = apply_liaison_rules([("dans", "ADP"), ("un instant".split()[0], "DET")])
    assert result[0].applies is True
    assert result[0].consonant == "z"


def test_multiple_pairs_in_a_chunk():
    # "les anciens amis" -> les|anciens obligatoire, anciens|amis obligatoire
    result = apply_liaison_rules(
        [("les", "DET"), ("anciens", "ADJ"), ("amis", "NOUN")]
    )
    assert len(result) == 2
    assert result[0].rule_type == "obligatoire"
    assert result[1].rule_type == "obligatoire"


def test_get_liaison_consonant_mapping():
    assert get_liaison_consonant("les") == "z"
    assert get_liaison_consonant("grand") == "t"
    assert get_liaison_consonant("un") == "n"
    assert get_liaison_consonant("amie") is None
