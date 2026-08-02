import pytest

from app.utils.address_normalizer import (
    build_full_address,
    normalize_address_key,
    spell_out_to_number,
    street_with_digits,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("três mil e quinhentos", 3500),
        ("tres mil e quinhentos", 3500),
        ("cento e vinte", 120),
        ("quarenta", 40),
        ("mil", 1000),
        ("dois mil e quarenta e cinco", 2045),
        ("cem", 100),
        ("dezessete", 17),
        ("um", 1),
        ("nove mil novecentos e noventa e nove", 9999),
    ],
)
def test_spell_out_to_number(text, expected):
    assert spell_out_to_number(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "   ", "florença", "rua das flores", "três mil e bananas", "e"],
)
def test_spell_out_to_number_refuses_to_guess(text):
    assert spell_out_to_number(text) is None


@pytest.mark.parametrize(
    "street,expected",
    [
        ("Rua três mil e quinhentos", "Rua 3500"),
        ("Rua Residencial Florença Um", "Rua Residencial Florença 1"),
        ("Avenida cento e vinte", "Avenida 120"),
        ("Rua Sete de Setembro", "Rua 7 de Setembro"),
    ],
)
def test_street_with_digits(street, expected):
    assert street_with_digits(street) == expected


@pytest.mark.parametrize(
    "street",
    ["Rua 3500", "Avenida Major Amarante", "Rua das Flores", ""],
)
def test_street_with_digits_returns_none_when_nothing_to_convert(street):
    assert street_with_digits(street) is None


def test_normalize_address_key_is_stable_across_writing_styles():
    a = normalize_address_key("Rua Três", "120", "Centro", "Vilhena")
    b = normalize_address_key("  rua   tres ", "120", "centro", "vilhena")
    c = normalize_address_key("RUA TRÊS.", "120,", "Centro!", "Vilhena")
    assert a == b == c == "rua tres 120 centro vilhena"


def test_normalize_address_key_distinguishes_different_addresses():
    assert normalize_address_key("Rua A", "10", "Centro") != normalize_address_key(
        "Rua A", "11", "Centro"
    )


def test_build_full_address():
    assert (
        build_full_address("Rua A", "10", "Centro", "76980-000", "CASA")
        == "Rua A, 10 - CASA - Centro - CEP 76980-000"
    )
    assert build_full_address("Rua A", "10", "Centro") == "Rua A, 10 - Centro"
