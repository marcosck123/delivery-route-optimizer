import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RouteForm from "@/components/RouteForm";

afterEach(() => {
  vi.restoreAllMocks();
});

async function fillAddress(
  street: string,
  number: string,
  neighborhood: string,
) {
  await userEvent.type(screen.getByLabelText("Rua"), street);
  await userEvent.type(screen.getByLabelText("Número"), number);
  await userEvent.type(screen.getByLabelText("Bairro"), neighborhood);
}

async function addAddress(street: string, number: string, neighborhood: string) {
  await fillAddress(street, number, neighborhood);
  await userEvent.click(screen.getByRole("button", { name: "+ Adicionar" }));
}

describe("RouteForm", () => {
  it("adiciona e remove endereços da lista", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await addAddress("Avenida Major Amarante", "1000", "Centro");
    expect(screen.getByText("Endereços (1)")).toBeInTheDocument();
    expect(
      screen.getByText("Avenida Major Amarante, 1000 — Centro"),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remover" }));
    expect(screen.queryByText("Endereços (1)")).not.toBeInTheDocument();
  });

  it("exige rua, número e bairro", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Rua"), "Rua A");
    await userEvent.click(screen.getByRole("button", { name: "+ Adicionar" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Preencha: número, bairro",
    );
    expect(screen.queryByText(/Endereços \(/)).not.toBeInTheDocument();
  });

  it("exige nome da rota antes de criar", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await addAddress("Rua A", "10", "Centro");
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    expect(screen.getByRole("status")).toHaveTextContent("Dê um nome para a rota");
  });

  it("exige pelo menos um endereço", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Nome da Rota"), "Rota 1");
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Adicione pelo menos um endereço",
    );
  });

  it("envia os endereços no formato da API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 7, name: "Rota 1" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onRouteCreated = vi.fn();

    render(<RouteForm token="meu-token" onRouteCreated={onRouteCreated} />);

    await userEvent.type(screen.getByLabelText("Nome da Rota"), "Rota 1");
    await fillAddress("Rua Residencial Florença Um", "8046", "Florença");
    await userEvent.type(screen.getByLabelText("Complemento"), "CASA");
    await userEvent.click(screen.getByRole("button", { name: "+ Adicionar" }));
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    await waitFor(() => expect(onRouteCreated).toHaveBeenCalledWith(7));

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/routes/");
    expect(options.headers.Authorization).toBe("Bearer meu-token");
    expect(JSON.parse(options.body)).toEqual({
      name: "Rota 1",
      deliveries: [
        {
          street: "Rua Residencial Florença Um",
          number: "8046",
          neighborhood: "Florença",
          cep: null,
          complement: "CASA",
        },
      ],
    });
  });

  it("mostra a mensagem humana quando a API recusa", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ detail: "Rota sem entregas" }),
      }),
    );

    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Nome da Rota"), "Rota 1");
    await addAddress("Rua A", "10", "Centro");
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Rota sem entregas"),
    );
    // não vaza status HTTP nem nome de API
    expect(screen.getByRole("status").textContent).not.toMatch(/400|fetch|API/);
  });
});
