import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import PhotoImport from "@/components/PhotoImport";

afterEach(() => {
  vi.restoreAllMocks();
});

const BLOCKS = [
  {
    raw_text:
      "MARCELA FLORINDA FUR...\nRUA RESIDENCIAL FLORENÇA-UM\nUM, 8046, CASA 76985662",
    order_id: "888030841672038",
    street: "RUA RESIDENCIAL FLORENÇA-UM",
    number: "8046",
    neighborhood: "RESIDENCIAL FLORENCA",
    complement: "CASA",
    cep: "76985-662",
  },
  {
    raw_text: "JOAO PEREIRA\nsem endereço legível",
    order_id: "888030841672039",
    street: "RUA X",
    number: null,
    neighborhood: null,
    complement: null,
    cep: null,
  },
];

function pngFile() {
  return new File(["fake-png-bytes"], "print.png", { type: "image/png" });
}

function mockUpload(response: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => response,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function uploadPrint() {
  await userEvent.upload(
    screen.getByLabelText(/Escolher print|Lendo a imagem/),
    pngFile(),
  );
}

describe("PhotoImport", () => {
  it("lê a imagem e mostra os blocos para revisão", async () => {
    mockUpload({ blocks: BLOCKS, message: "2 endereço(s) lido(s) — confira antes de adicionar." });

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();

    expect(await screen.findByText("Confira o que foi lido (2):")).toBeInTheDocument();
    expect(screen.getByLabelText("Rua 1")).toHaveValue(
      "RUA RESIDENCIAL FLORENÇA-UM",
    );
    expect(screen.getByLabelText("Número 1")).toHaveValue("8046");
    // complemento e CEP chegam preenchidos pelo parser, não vazios
    expect(screen.getByLabelText("Complemento 1")).toHaveValue("CASA");
    expect(screen.getByLabelText("CEP 1")).toHaveValue("76985-662");
    expect(screen.getByText("Pedido 888030841672038")).toBeInTheDocument();
    // o texto lido fica à vista para conferência
    expect(screen.getByText(/MARCELA FLORINDA FUR/)).toBeInTheDocument();
  });

  it("deixa os campos vazios quando o OCR não conseguiu separar", async () => {
    mockUpload({ blocks: BLOCKS, message: "2 endereço(s) lido(s)" });

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();

    expect(await screen.findByLabelText("Número 2")).toHaveValue("");
    expect(screen.getByText(/sem endereço legível/)).toBeInTheDocument();
  });

  it("exige completar os campos obrigatórios antes de adicionar", async () => {
    mockUpload({ blocks: BLOCKS, message: "2 endereço(s) lido(s)" });

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();
    await userEvent.click(
      await screen.findByRole("button", { name: "Adicionar à rota" }),
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Complete rua, número e bairro de 1 endereço(s)",
    );
  });

  it("envia o número do pedido lido como jet_order_id", async () => {
    const fetchMock = mockUpload({
      blocks: [BLOCKS[0]],
      message: "1 endereço(s) lido(s)",
    });

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();
    await screen.findByLabelText("Rua 1");

    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 10 }),
    });
    await userEvent.click(screen.getByRole("button", { name: "Adicionar à rota" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.jet_order_id).toBe("888030841672038");
    expect(body.cep).toBe("76985-662");
    expect(body.complement).toBe("CASA");
  });

  it("envia os endereços corrigidos e avisa o pai", async () => {
    const fetchMock = mockUpload({
      blocks: [BLOCKS[0]],
      message: "1 endereço(s) lido(s)",
    });
    const onAdded = vi.fn();

    render(<PhotoImport routeId={3} token="meu-token" onAdded={onAdded} />);
    await uploadPrint();

    // ela corrige o dígito que o OCR errou
    const number = await screen.findByLabelText("Número 1");
    await userEvent.clear(number);
    await userEvent.type(number, "8047");

    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 10 }),
    });
    await userEvent.click(screen.getByRole("button", { name: "Adicionar à rota" }));

    await waitFor(() => expect(onAdded).toHaveBeenCalled());

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(lastCall[0]).toContain("/api/routes/3/deliveries/");
    expect(JSON.parse(lastCall[1].body)).toEqual({
      street: "RUA RESIDENCIAL FLORENÇA-UM",
      number: "8047",
      neighborhood: "RESIDENCIAL FLORENCA",
      cep: "76985-662",
      complement: "CASA",
      jet_order_id: "888030841672038",
    });
  });

  it("permite descartar um bloco lido errado", async () => {
    mockUpload({ blocks: BLOCKS, message: "2 endereço(s) lido(s)" });

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();

    await userEvent.click(
      await screen.findByRole("button", { name: "Descartar endereço 2" }),
    );

    expect(screen.getByText("Confira o que foi lido (1):")).toBeInTheDocument();
  });

  it("mostra só a mensagem humana quando a leitura falha", async () => {
    mockUpload({ detail: "Não consegui ler a imagem" }, false, 500);

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Não consegui ler a imagem");
    expect(status.textContent).not.toMatch(/500|fetch|tesseract/i);
  });

  it("avisa quando a imagem não tinha endereço nenhum", async () => {
    mockUpload({
      blocks: [],
      message: "Não encontrei endereços nessa imagem. Tente dar zoom antes do print.",
    });

    render(<PhotoImport routeId={3} token="t" onAdded={vi.fn()} />);
    await uploadPrint();

    expect(await screen.findByRole("status")).toHaveTextContent("Tente dar zoom");
  });
});
