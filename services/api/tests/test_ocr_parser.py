"""Parser da tela de entregas da J&T, exercitado sobre texto REAL de OCR.

O fixture principal é a saída literal do Tesseract num print de 3 entregas —
com número de pedido corrompido, endereço quebrado em várias linhas e cards
inteiros colados numa linha só. Testar sobre texto limpo dava falsa confiança:
o parser passava nos testes e devolvia `blocks: []` na tela de verdade.
"""

import pytest

from app.utils.ocr import (
    is_order_id,
    is_ui_noise,
    is_watermark,
    parse_address_fields,
    parse_addresses,
    read_order_id,
)

# Saída literal do Tesseract (print com 3 entregas). Copiada sem edição.
REAL_OCR_TEXT = """\
Re
& Nú...dido * Por favor, Insira

Recibo de Entrega . Pacote
Assinado
Transferên... pendente(37) problemático
Últimos 7 dias ” Se Filtro de datav Roteirização

| ss8030841672038 O GU

| MARCELA FLORINDA FUR...

1;RUA RESIDENCIAL FLORENÇA-UM O nav...ção
RESIDENCIAL FLORENCA Vilhena SS E)
RO RUA RESIDENCIAL ori o eo) Telefone
UM, 8046, CASA 76985662 q”
eo

2026-08-01 18:24:00' Registro de anomalia ) ) Registro de anomalia ) anomalia ) Coser ) O) |A STse8030842763869 [noMARCELA FLORINDA FUR...RUA RESIDENCIAL FLORENÇA-UMEK “RESIDENCIAL FLORENCA Vilhena“<BO RUA RESIDENCIAL FLORENÇA-* UM, 8046, CASA 769856622026-08-01 18:23:57 Ssvanderlei Viera fochaRua Residencial Florença-Três (E) nav...çãoRESIDENCIAL FLORENCA VilhenaRO Rua Residencial Elorenca-Três (O Telefone
"""

# Texto ideal, do jeito que a tela seria se o OCR fosse perfeito. Mantido como
# regressão: o parser tem que continuar dando conta do caso fácil.
CLEAN_OCR_TEXT = """\
Recibo de Transferência
Entrega pendente   Assinado   Pacote problemático
888030841672038
MARCELA FLORINDA FUR...
RUA RESIDENCIAL FLORENÇA-UM
RESIDENCIAL FLORENCA Vilhena
RO RUA RESIDENCIAL FLORENÇA-
UM, 8046, CASA 76985662
2026-08-01 18:24:00
[navegação]  Telefone  Registro de anomalia  Assinar
888030841672039
VANDERLEI VIERA ROCHA
RUA RESIDENCIAL FLORENÇA-TRÊS
RESIDENCIAL FLORENCA Vilhena
RO RUA RESIDENCIAL FLORENÇA-
TRÊS, 1290, FUNDOS 76985663
2026-08-01 18:25:00
"""


@pytest.fixture
def blocks():
    return parse_addresses(REAL_OCR_TEXT)


# ------------------------------------------------------ o caso que quebrava


def test_real_screen_yields_three_deliveries(blocks):
    """Antes desta correção, este mesmo texto devolvia []."""
    assert len(blocks) == 3


def test_marcela_first_card_is_fully_extracted(blocks):
    marcela = blocks[0]
    assert marcela["order_id"] == "8030841672038"
    assert marcela["street"] == "RUA RESIDENCIAL FLORENÇA-UM"
    assert marcela["number"] == "8046"
    assert marcela["complement"] == "CASA"
    assert marcela["cep"] == "76985-662"
    assert marcela["neighborhood"] == "RESIDENCIAL FLORENCA"


def test_marcela_second_card_is_extracted_despite_the_glued_line(blocks):
    """O 2º card vem colado no rodapé do 1º, sem quebra de linha nenhuma."""
    second = blocks[1]
    assert second["order_id"] == "8030842763869"
    assert "FLOREN" in second["street"]  # "-UMEK": lixo de OCR que ela corrige
    assert second["number"] == "8046"
    assert second["complement"] == "CASA"
    assert second["cep"] == "76985-662"


def test_third_delivery_survives_without_a_readable_order_id(blocks):
    """O logradouro ancora o card quando o número do pedido não sobreviveu."""
    third = blocks[2]
    assert third["order_id"] is None
    assert third["street"] == "Rua Residencial Florença-Três"
    # esses campos não estão no trecho — ficam vazios, não inventados
    assert third["number"] is None
    assert third["cep"] is None


def test_app_header_never_becomes_a_delivery(blocks):
    joined = " ".join(block["street"] or "" for block in blocks)
    for noise in ["Recibo", "Roteirização", "Filtro", "Insira", "Últimos"]:
        assert noise not in joined


def test_buttons_are_not_captured_as_address(blocks):
    for block in blocks:
        assert "Registro de anomalia" not in (block["street"] or "")
        assert "Telefone" not in (block["street"] or "")


def test_two_orders_at_the_same_address_stay_separate(blocks):
    """Os dois pedidos da Marcela são a mesma casa — e continuam dois cards."""
    assert blocks[0]["street"] == "RUA RESIDENCIAL FLORENÇA-UM"
    assert blocks[0]["number"] == blocks[1]["number"]
    assert blocks[0]["order_id"] != blocks[1]["order_id"]


# ------------------------------------------------------ número do pedido


@pytest.mark.parametrize(
    "text,expected",
    [
        ("| ss8030841672038 O GU", "8030841672038"),  # prefixo virou letra
        ("STse8030842763869 [no", "8030842763869"),
        ("888030841672038", "888030841672038"),
        ("88803084:672038", "88803084672038"),  # sujeira no meio do número
        ("2026-08-01 18:24:00", None),  # timestamp também é dígito longo
        ("8046", None),
        ("76985662", None),  # CEP não é pedido
    ],
)
def test_read_order_id(text, expected):
    assert read_order_id(text) == expected


def test_cep_glued_to_the_date_is_not_read_as_an_order_id(blocks):
    """"...CASA 769856622026-08-01" tem 12 dígitos seguidos e enganava o split."""
    assert all(block["order_id"] != "769856622026" for block in blocks)
    assert blocks[1]["cep"] == "76985-662"  # o CEP sobreviveu inteiro


def test_order_id_is_not_mistaken_for_watermark():
    assert is_watermark("888030841672038") is False
    assert is_watermark("82736451928374651928") is True


# ------------------------------------------------------- campos isolados


def test_cep_without_hyphen_is_formatted():
    assert parse_address_fields("RUA A, 10, CASA 76985662")["cep"] == "76985-662"


def test_cep_with_hyphen_is_kept():
    assert parse_address_fields("RUA A, 10 76985-662")["cep"] == "76985-662"


def test_number_between_commas():
    assert parse_address_fields("RUA A, 8046, CASA")["number"] == "8046"


def test_number_before_the_complement_without_commas():
    assert parse_address_fields("RUA DOS IPES 45 CASA")["number"] == "45"


def test_word_um_in_the_street_name_is_not_a_number():
    fields = parse_address_fields("RUA RESIDENCIAL FLORENÇA-UM, 8046, CASA")
    assert fields["number"] == "8046"
    assert fields["street"].endswith("UM")


def test_ocr_digit_confusion_is_repaired():
    assert parse_address_fields("RUA A, 8O46, CASA")["number"] == "8046"


def test_ambiguous_number_is_left_empty():
    """Sujeira demais: melhor campo vazio que número errado que ela não nota."""
    assert parse_address_fields("RUA A, 8X4G, CASA")["number"] is None


def test_complement_does_not_swallow_ocr_debris():
    """"CASA 76985662 q”" tem que virar só "CASA"."""
    assert parse_address_fields("RUA A, 8046, CASA 76985662 q”")["complement"] == "CASA"


def test_complement_keeps_a_real_unit_designation():
    assert parse_address_fields("RUA A, 10, APTO 302")["complement"] == "APTO 302"
    assert parse_address_fields("RUA A, 10, BLOCO B")["complement"] == "BLOCO B"


def test_street_stops_at_an_ocr_seam():
    """A aspa colada na palavra marca emenda entre elementos da tela."""
    fields = parse_address_fields('RUA RESIDENCIAL FLORENÇA-UM “RESIDENCIAL FLORENCA')
    assert fields["street"] == "RUA RESIDENCIAL FLORENÇA-UM"


def test_street_scoring_prefers_the_less_corrupted_repetition():
    """Uma repetição vem limpa e a outra destruída — vence a que sobreviveu."""
    text = "RUA RESIDENCIAL FLORENÇA-UM O RO RUA RESIDENCIAL ori o eo) UM, 8046, CASA"
    assert parse_address_fields(text)["street"] == "RUA RESIDENCIAL FLORENÇA-UM"


def test_missing_fields_are_left_empty():
    fields = parse_address_fields("Rua Residencial Florença-Três")
    assert fields["street"] == "Rua Residencial Florença-Três"
    assert fields["number"] is None
    assert fields["complement"] is None
    assert fields["cep"] is None


# --------------------------------------------------------------- descarte


def test_card_without_a_street_is_dropped():
    assert parse_addresses("888030841672040 FULANO DE TAL 2026-08-01 18:30:00") == []


def test_text_without_any_order_id_or_street_yields_nothing():
    assert parse_addresses("Recibo de Transferência\nEntrega pendente\n") == []


def test_empty_text():
    assert parse_addresses("") == []
    assert parse_addresses("\n\n  \n") == []


def test_ui_noise_never_eats_a_street_named_navegantes():
    """"nav" está na blocklist, mas AVENIDA NAVEGANTES é endereço."""
    assert is_ui_noise("[navegação]") is True
    assert is_ui_noise("AVENIDA NAVEGANTES, 100") is False

    blocks = parse_addresses(
        "888030841672041\nFULANO\nAVENIDA NAVEGANTES\nCENTRO Vilhena\n"
        "RO AVENIDA NAVEGANTES, 100, CASA 76980000\n2026-08-01 18:30:00\n"
    )
    assert len(blocks) == 1
    assert blocks[0]["street"] == "AVENIDA NAVEGANTES"
    assert blocks[0]["number"] == "100"


# ------------------------------------------------- regressão (texto limpo)


def test_clean_text_still_parses():
    blocks = parse_addresses(CLEAN_OCR_TEXT)

    assert len(blocks) == 2
    assert blocks[0]["order_id"] == "888030841672038"
    assert blocks[0]["street"] == "RUA RESIDENCIAL FLORENÇA-UM"
    assert blocks[0]["number"] == "8046"
    assert blocks[0]["cep"] == "76985-662"
    assert blocks[1]["number"] == "1290"
    assert blocks[1]["complement"] == "FUNDOS"


def test_dash_variants_are_normalized(blocks):
    for block in blocks:
        assert "–" not in (block["street"] or "")


def test_raw_text_is_kept_for_review(blocks):
    assert "MARCELA" in blocks[0]["raw_text"]
    assert all(block["raw_text"] for block in blocks)


def test_is_order_id_helper():
    assert is_order_id("| ss8030841672038 O GU") is True
    assert is_order_id("MARCELA FLORINDA FUR...") is False
