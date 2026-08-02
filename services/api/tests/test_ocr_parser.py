"""Parser tailored to the J&T delivery screen.

Everything here runs over strings: Tesseract is mocked elsewhere, and what
matters is that the fixed structure of the screen is exploited correctly.
"""

import pytest

from app.utils.ocr import (
    is_order_id,
    is_ui_noise,
    is_watermark,
    parse_address_fields,
    parse_addresses,
)

# Texto como sai do OCR da tela real: cabeçalho do app, dois cards, botões.
SCREEN_OCR_TEXT = """\
Recibo de Transferência
Entrega pendente   Assinado   Pacote problemático
Últimos 7 dias   Filtro de data   Roteirização
Por favor, insira o Número do pedido para procurar
888030841672038
MARCELA FLORINDA FUR...
RUA RESIDENCIAL FLORENÇA–UM
RESIDENCIAL FLORENCA Vilhena
RO RUA RESIDENCIAL FLORENÇA–
UM, 8046, CASA 76985662
2026-08-01 18:24:00
[navegação]  Telefone  Registro de anomalia  Assinar
888030841672039
VANDERLEI VIERA ROCHA
RUA RESIDENCIAL FLORENÇA–TRÊS
RESIDENCIAL FLORENCA Vilhena
RO RUA RESIDENCIAL FLORENÇA–
TRÊS, 1290, FUNDOS 76985663
2026-08-01 18:25:00
[navegação]  Telefone  Registro de anomalia  Assinar
"""


@pytest.fixture
def blocks():
    return parse_addresses(SCREEN_OCR_TEXT)


# ------------------------------------------------------------ segmentação


def test_splits_by_order_id_not_by_ui_lines(blocks):
    assert len(blocks) == 2


def test_app_header_does_not_become_a_delivery(blocks):
    joined = " ".join(block["raw_text"] for block in blocks)
    for noise in ["Recibo de Transfer", "Filtro de data", "Roteirização", "procurar"]:
        assert noise not in joined

    for block in blocks:
        assert "Recibo" not in (block["street"] or "")


def test_buttons_after_the_date_are_dropped(blocks):
    for block in blocks:
        assert "Registro de anomalia" not in block["raw_text"]
        assert "Assinar" not in (block["street"] or "")


def test_order_id_is_captured(blocks):
    assert [block["order_id"] for block in blocks] == [
        "888030841672038",
        "888030841672039",
    ]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("888030841672038", True),
        ("88803084167203", True),  # 14 dígitos: OCR comeu um
        ("8880308416720384", True),  # 16 dígitos: OCR somou um
        ("8046", False),
        ("76985662", False),
        ("2026-08-01", False),
    ],
)
def test_is_order_id(line, expected):
    assert is_order_id(line) is expected


def test_order_id_is_not_mistaken_for_watermark():
    """O marcador de bloco é uma sequência longa de dígitos — não pode ser peneirado."""
    assert is_watermark("888030841672038") is False
    assert is_watermark("82736451928374651928") is True  # marca d'água de verdade


# ------------------------------------------------------------------ campos


def test_extracts_the_marcela_card(blocks):
    marcela = blocks[0]
    assert marcela["street"] == "RUA RESIDENCIAL FLORENÇA-UM"
    assert marcela["number"] == "8046"
    assert "CASA" in marcela["complement"]
    assert marcela["cep"] == "76985-662"


def test_extracts_the_vanderlei_card(blocks):
    vanderlei = blocks[1]
    assert vanderlei["street"] == "RUA RESIDENCIAL FLORENÇA-TRÊS"
    assert vanderlei["number"] == "1290"
    assert "FUNDOS" in vanderlei["complement"]
    assert vanderlei["cep"] == "76985-663"


def test_word_um_in_the_street_name_is_not_read_as_a_number(blocks):
    """"Florença-Um" é nome de rua; só dígito vira número."""
    marcela = blocks[0]
    assert marcela["number"] == "8046"
    assert marcela["street"].endswith("UM")


def test_uses_the_second_repetition_with_the_house_number(blocks):
    """A repetição 1 não tem número; o parser tem que pegar a última ocorrência."""
    assert all(block["number"] for block in blocks)


def test_neighborhood_comes_from_the_discarded_repetition(blocks):
    assert blocks[0]["neighborhood"] == "RESIDENCIAL FLORENCA"


def test_raw_text_is_kept_for_review(blocks):
    assert "MARCELA FLORINDA FUR" in blocks[0]["raw_text"]
    assert "VANDERLEI VIERA ROCHA" in blocks[1]["raw_text"]


def test_dash_variants_are_normalized(blocks):
    for block in blocks:
        assert "–" not in block["street"]


# ------------------------------------------------- campos, casos isolados


def test_cep_without_hyphen_is_formatted():
    fields = parse_address_fields("RUA A, 10, CASA 76985662")
    assert fields["cep"] == "76985-662"


def test_cep_with_hyphen_is_kept():
    fields = parse_address_fields("RUA A, 10 76985-662")
    assert fields["cep"] == "76985-662"


def test_address_without_cep():
    fields = parse_address_fields("RUA A, 10, CASA")
    assert fields["cep"] is None
    assert fields["number"] == "10"


def test_number_glued_to_the_street_name():
    fields = parse_address_fields("RUA DOS IPES 45")
    assert fields["street"] == "RUA DOS IPES"
    assert fields["number"] == "45"


def test_ocr_digit_confusion_is_repaired():
    fields = parse_address_fields("RUA A, 8O46, CASA")
    assert fields["number"] == "8046"


def test_ambiguous_number_is_left_as_read():
    """Sujeira demais: entrega como veio para ela corrigir, sem inventar."""
    fields = parse_address_fields("RUA A, 8X4G, CASA")
    assert fields["number"] is None


def test_address_without_number():
    fields = parse_address_fields("RUA A, CASA")
    assert fields["street"] == "RUA A"
    assert fields["number"] is None


# --------------------------------------------------------------- descarte


def test_card_without_a_street_is_dropped():
    text = "888030841672040\nFULANO DE TAL\n2026-08-01 18:30:00\nAssinar\n"
    assert parse_addresses(text) == []


def test_text_without_any_order_id_yields_nothing():
    assert parse_addresses("Recibo de Transferência\nEntrega pendente\n") == []


def test_empty_text():
    assert parse_addresses("") == []
    assert parse_addresses("\n\n  \n") == []


def test_ui_noise_never_eats_a_street_named_navegantes():
    """"nav" está na blocklist, mas AVENIDA NAVEGANTES é endereço."""
    assert is_ui_noise("[navegação]") is True
    assert is_ui_noise("AVENIDA NAVEGANTES, 100") is False

    text = (
        "888030841672041\nFULANO\nAVENIDA NAVEGANTES\n"
        "CENTRO Vilhena\nRO AVENIDA NAVEGANTES, 100, CASA 76980000\n"
        "2026-08-01 18:30:00\n"
    )
    blocks = parse_addresses(text)
    assert len(blocks) == 1
    assert blocks[0]["street"] == "AVENIDA NAVEGANTES"
    assert blocks[0]["number"] == "100"


def test_two_orders_at_the_same_address_stay_separate():
    """Dois pedidos na mesma casa são duas entregas — sem dedup."""
    card = (
        "{order}\nMARCELA FLORINDA FUR...\nRUA RESIDENCIAL FLORENÇA-UM\n"
        "RESIDENCIAL FLORENCA Vilhena\nRO RUA RESIDENCIAL FLORENÇA-\n"
        "UM, 8046, CASA 76985662\n2026-08-01 18:24:00\n"
    )
    text = card.format(order="888030841672038") + card.format(order="888030841672099")

    blocks = parse_addresses(text)
    assert len(blocks) == 2
    assert blocks[0]["street"] == blocks[1]["street"]
    assert blocks[0]["number"] == blocks[1]["number"]
    assert blocks[0]["order_id"] != blocks[1]["order_id"]
