import io

import pytest

from tests.test_ocr import SAMPLE_OCR_TEXT, make_screenshot


@pytest.fixture
def fake_tesseract(monkeypatch):
    """O binário do Tesseract não existe em todo ambiente; o resto é real."""
    monkeypatch.setattr(
        "app.utils.ocr.pytesseract.image_to_string",
        lambda image, lang=None: SAMPLE_OCR_TEXT,
    )


def create_route(client, auth_headers, name="Rota da foto"):
    return client.post(
        "/api/routes/", headers=auth_headers, json={"name": name, "deliveries": []}
    ).json()


def upload(client, auth_headers, route_id, payload=None, filename="print.png"):
    return client.post(
        f"/api/routes/{route_id}/ocr-upload",
        headers=auth_headers,
        files={
            "file": (
                filename,
                io.BytesIO(payload if payload is not None else make_screenshot()),
                "image/png",
            )
        },
    )


def test_ocr_upload_returns_blocks_for_review(client, auth_headers, fake_tesseract):
    route = create_route(client, auth_headers)

    response = upload(client, auth_headers, route["id"])
    assert response.status_code == 200

    body = response.json()
    # dois cards de verdade — o cabeçalho do app não entra na conta
    assert len(body["blocks"]) == 2
    assert "2 endereço(s) lido(s)" in body["message"]

    first = body["blocks"][0]
    assert first["order_id"] == "888030841672038"
    assert first["street"] == "RUA RESIDENCIAL FLORENÇA-UM"
    assert first["number"] == "8046"
    assert first["neighborhood"] == "RESIDENCIAL FLORENCA"
    assert "CASA" in first["complement"]
    assert first["cep"] == "76985-662"
    assert "MARCELA FLORINDA FUR" in first["raw_text"]


def test_ocr_upload_does_not_return_ui_chrome(client, auth_headers, fake_tesseract):
    """O bug que motivou a calibração: abas e botões viravam 'endereço'."""
    route = create_route(client, auth_headers)
    blocks = upload(client, auth_headers, route["id"]).json()["blocks"]

    streets = [block["street"] for block in blocks]
    for noise in ["Recibo", "Entrega", "Assinar", "Filtro", "Roteirização"]:
        assert all(noise not in (street or "") for street in streets)

    # e todo card volta com os campos preenchidos, não vazios
    assert all(block["street"] and block["number"] for block in blocks)


def test_ocr_upload_does_not_create_deliveries(client, auth_headers, fake_tesseract):
    """Nada é gravado antes de ela revisar."""
    route = create_route(client, auth_headers)
    upload(client, auth_headers, route["id"])

    updated = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert updated["deliveries"] == []


def test_ocr_upload_with_unreadable_image(client, auth_headers, fake_tesseract):
    route = create_route(client, auth_headers)

    response = upload(client, auth_headers, route["id"], payload=b"isso nao e imagem")
    assert response.status_code == 400
    assert response.json()["detail"] == "Não consegui ler a imagem"


def test_ocr_upload_when_tesseract_is_missing(client, auth_headers, monkeypatch):
    """Sem o binário instalado, ela vê a mensagem humana — não um stack trace."""

    def explode(image, lang=None):
        raise OSError("tesseract is not installed or it's not in your PATH")

    monkeypatch.setattr("app.utils.ocr.pytesseract.image_to_string", explode)
    route = create_route(client, auth_headers)

    response = upload(client, auth_headers, route["id"])
    assert response.status_code == 500

    detail = response.json()["detail"]
    assert detail == "Não consegui ler a imagem"
    assert "tesseract" not in detail.lower()
    assert "PATH" not in detail


def test_ocr_upload_without_recognizable_text(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.utils.ocr.pytesseract.image_to_string", lambda image, lang=None: "   \n\n"
    )
    route = create_route(client, auth_headers)

    body = upload(client, auth_headers, route["id"]).json()
    assert body["blocks"] == []
    assert "zoom" in body["message"]


def test_ocr_upload_is_scoped_to_owner(client, auth_headers, fake_tesseract):
    route = create_route(client, auth_headers)
    other = client.post(
        "/api/auth/register",
        json={"email": "curioso@example.com", "password": "password123"},
    ).json()["access_token"]

    response = upload(
        client, {"Authorization": f"Bearer {other}"}, route["id"]
    )
    assert response.status_code == 404


def test_ocr_upload_requires_authentication(client, fake_tesseract):
    response = client.post(
        "/api/routes/1/ocr-upload",
        files={"file": ("print.png", io.BytesIO(make_screenshot()), "image/png")},
    )
    assert response.status_code == 401


def test_reviewed_blocks_enter_the_normal_flow(client, auth_headers, fake_tesseract):
    """O que ela revisou vira entrega pelo mesmo endpoint da Parte 1."""
    route = create_route(client, auth_headers)
    blocks = upload(client, auth_headers, route["id"]).json()["blocks"]

    corrected = {
        "street": blocks[0]["street"],
        "number": blocks[0]["number"],
        "neighborhood": "Residencial Florença",
        "complement": blocks[0]["complement"],
        "cep": blocks[0]["cep"],
        "jet_order_id": blocks[0]["order_id"],
    }
    created = client.post(
        f"/api/routes/{route['id']}/deliveries/",
        headers=auth_headers,
        json=corrected,
    )

    assert created.status_code == 201
    body = created.json()
    assert body["geocode_status"] == "pending"
    assert body["address"].startswith("RUA RESIDENCIAL FLORENÇA-UM, 8046")
    # o número do pedido lido da tela vira o jet_order_id da entrega
    assert body["jet_order_id"] == "888030841672038"
