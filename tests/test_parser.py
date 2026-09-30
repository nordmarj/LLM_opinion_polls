import pytest

from survey.config import load_config
from survey.parser import code_credences, code_pick, extract_tag, parse_response

CFG = load_config()
QM = CFG.questions["qm_full"]
BIN = CFG.questions["qm_binary"]
DT = CFG.questions["dt_control"]


@pytest.mark.parametrize("answer,code", [
    ("Many-worlds (Everett)", "many_worlds"),
    ("Everettian quantum mechanics", "many_worlds"),
    ("MWI", "many_worlds"),
    ("the relative-state formulation", "many_worlds"),
    ("Many‑worlds", "many_worlds"),                      # non-breaking hyphen
    ("**Many-worlds**", "many_worlds"),
    ("Copenhagen / standard interpretation", "copenhagen"),
    ("The Copenhagen interpretation", "copenhagen"),
    ("Bohmian mechanics (pilot wave)", "bohmian"),
    ("de Broglie-Bohm pilot-wave theory", "bohmian"),
    ("Objective collapse (GRW / Penrose)", "objective_collapse"),
    ("GRW", "objective_collapse"),
    ("QBism", "qbism_epistemic"),
    ("Relational quantum mechanics", "relational"),
    ("Consistent histories", "consistent_histories"),
    ("No preference / agnostic", "agnostic"),
    ("Agnostic", "agnostic"),
])
def test_qm_synonyms(answer, code):
    p = code_pick(answer, QM)
    assert p.status == "ok" and p.code == code


def test_other_naming_listed_option_maps_to_that_option():
    p = code_pick("Other: decoherent histories", QM)
    assert p.code == "consistent_histories"


def test_other_unlisted_keeps_text():
    p = code_pick("Other (transactional interpretation)", QM)
    assert p.code == "other" and "transactional" in p.other_text


def test_multiple_options_go_to_judge():
    p = code_pick("Copenhagen or QBism", QM)
    assert p.status == "unresolved"


def test_unknown_goes_to_judge():
    assert code_pick("I'd rather not say", QM).status == "unresolved"


def test_binary():
    assert code_pick("many-worlds", BIN).code == "many_worlds"
    p = code_pick("other: Copenhagen", BIN)
    assert p.code == "other" and p.other_text == "Copenhagen"


def test_many_worlds_does_not_match_inside_other_words():
    # "worlds" alone or "many" alone must not trigger many_worlds
    assert code_pick("worlds of possibility", QM).status == "unresolved"


@pytest.mark.parametrize("answer,code", [
    ("Functional Decision Theory (FDT)", "ldt"),
    ("Updateless decision theory", "ldt"),
    ("Causal decision theory", "cdt"),
    ("EDT", "edt"),
])
def test_dt_synonyms(answer, code):
    assert code_pick(answer, DT).code == code


def test_extract_last_tag_and_ignore_placeholder():
    text = "Format: <answer>...</answer>\n\n<answer>Many-worlds</answer> because..."
    assert extract_tag(text, "answer") == "Many-worlds"


def test_parse_response_missing_tag():
    assert parse_response("I think many-worlds.", QM, "pick").status == "missing"


def test_parse_response_theory_tag():
    assert parse_response("<theory>FDT</theory>", DT, "pick").code == "ldt"


def test_credences_ok_and_fills_zeros():
    p = code_credences('<credences>{"many_worlds": 60, "copenhagen": 40}</credences>', QM)
    assert p.status == "ok" and p.code == "many_worlds"
    assert p.credences["bohmian"] == 0.0 and sum(p.credences.values()) == 100


def test_credences_unit_scale_rescaled():
    p = code_credences('<credences>{"many_worlds": 0.7, "bohmian": 0.3}</credences>', QM)
    assert p.status == "ok" and p.credences["many_worlds"] == pytest.approx(70)


def test_credences_bad_sum():
    p = code_credences('<credences>{"many_worlds": 70, "bohmian": 70}</credences>', QM)
    assert p.status == "unresolved"


def test_credences_label_keys_mapped():
    p = code_credences('<credences>{"Many-worlds (Everett)": 50, "QBism": 50}</credences>', QM)
    assert p.status == "ok" and p.credences["qbism_epistemic"] == 50
