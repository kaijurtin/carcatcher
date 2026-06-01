"""Unit tests for the deterministic VW ID model categorizer."""

from __future__ import annotations

from carcatcher.db.models import Listing
from carcatcher.normalization.model_categorizer import apply_categorization, categorize


def _listing(**kw) -> Listing:
    base = dict(source="kleinanzeigen", source_id="x", url="x", raw_title="")
    base.update(kw)
    return Listing(**base)


# --- categorize(): naming canonicalization --------------------------------- #

def test_canonicalizes_spaced_and_dotless_model_names():
    for raw in ("ID 4", "id4", "ID.4", "iD.4"):
        result = categorize("VW", raw, None, 2022, None)
        assert result.matched is True
        assert result.model == "ID.4"
        assert result.make == "Volkswagen"


def test_detects_model_from_title_when_fields_empty():
    # AI-off mode: make/model are None, only the title carries the signal.
    result = categorize(None, None, None, 2023, None, text="VW ID. Buzz Pro Elektro")
    assert result.matched is True
    assert result.model == "ID. Buzz"
    assert result.make == "Volkswagen"


def test_parses_trim_longest_alias_first():
    assert categorize("Volkswagen", "ID.7", "Pro S Limited", 2024, None).variant == "Pro S"
    assert categorize("Volkswagen", "ID.3", "Pro Performance", 2022, None).variant == "Pro"
    assert categorize("Volkswagen", "ID.4", "GTX 4MOTION", 2023, None).variant == "GTX"


# --- categorize(): battery fill + snap ------------------------------------- #

def test_fills_battery_for_unambiguous_trim_when_missing():
    # ID.7 Pro S maps unambiguously to 86 kWh usable.
    assert categorize("Volkswagen", "ID.7", "Pro S", 2024, None).battery_kwh == 86.0
    # ID.4 GTX -> 77 kWh.
    assert categorize("Volkswagen", "ID.4", "GTX", 2023, None).battery_kwh == 77.0


def test_leaves_battery_none_when_trim_is_ambiguous():
    # ID.4 Pro spans 77/79 across years -> no confident fill.
    assert categorize("Volkswagen", "ID.4", "Pro", 2022, None).battery_kwh is None


def test_snaps_near_spec_battery_to_canonical_value():
    # 85.4 is within tolerance of the 86.0 ID.7 spec -> snapped.
    assert categorize("Volkswagen", "ID.7", "Pro S", 2024, 85.4).battery_kwh == 86.0


def test_keeps_far_battery_value_unchanged():
    # 64 is not near any ID.7 spec (77/86) -> left as the source provided it.
    assert categorize("Volkswagen", "ID.7", "Pro", 2024, 64.0).battery_kwh == 64.0


def test_does_not_fill_battery_for_implausible_year():
    assert categorize("Volkswagen", "ID.7", "Pro S", 2010, None).battery_kwh is None


# --- categorize(): no-op cases --------------------------------------------- #

def test_no_op_for_other_make():
    assert categorize("BMW", "i4", None, 2022, None).matched is False


def test_no_op_for_vw_non_id_model():
    assert categorize("Volkswagen", "Golf", "GTI", 2021, None).matched is False


def test_no_op_does_not_match_substring_like_words():
    # "raid"/"covid" must not trip the \bid<token> pattern.
    assert categorize("Volkswagen", None, None, 2022, None, text="Touran Raid4 paket").matched is False


# --- apply_categorization(): non-destructive in place ---------------------- #

def test_apply_canonicalizes_and_gap_fills():
    li = _listing(raw_title="VW ID.4 GTX", make="VW", model="ID 4", variant=None, year=2023)
    changed = apply_categorization(li)
    assert changed is True
    assert (li.make, li.model, li.variant, li.battery_kwh) == ("Volkswagen", "ID.4", "GTX", 77.0)


def test_apply_does_not_clobber_confident_variant():
    li = _listing(raw_title="VW ID.3", make="Volkswagen", model="ID.3", variant="Pro Business", year=2022)
    apply_categorization(li)
    assert li.variant == "Pro Business"  # richer Haiku variant preserved


def test_apply_no_op_returns_false_for_non_id():
    li = _listing(raw_title="VW Golf", make="Volkswagen", model="Golf", year=2020)
    assert apply_categorization(li) is False
