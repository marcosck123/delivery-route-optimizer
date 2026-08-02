import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import SavedAddresses from "@/components/SavedAddresses";
import type { SavedAddress } from "@/lib/types";

// O mapa Leaflet não roda em jsdom; aqui interessa o fluxo da tela.
vi.mock("@/components/PinMap", () => ({
  default: ({ position }: { position: { latitude: number } }) => (
    <div data-testid="pin-map">pin em {position.latitude}</div>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

const ENTRIES: SavedAddress[] = [
  {
    id: 1,
    address: "Rua Osório, 250 - Centro",
    address_key: "rua osorio 250 centro vilhena",
    latitude: -12.73,
    longitude: -60.14,
    source: "google",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
  },
  {
    id: 2,
    address: "Rua B, 20 - Jardim",
    address_key: "rua b 20 jardim vilhena",
    latitude: -12.75,
    longitude: -60.16,
    source: "manual",
    created_at: "2026-08-02T10:00:00Z",
    updated_at: "2026-08-02T10:00:00Z",
  },
];

function mockFetch(response: unknown, ok = true, status = 200) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok, status, json: async () => response });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("SavedAddresses", () => {
  it("lista os endereços salvos com a origem", async () => {
    mockFetch(ENTRIES);

    render(<SavedAddresses token="t" />);

    expect(await screen.findByText("Rua Osório, 250 - Centro")).toBeInTheDocument();
    expect(screen.getByText(/Google/)).toBeInTheDocument();
    expect(screen.getByText(/Corrigido por você/)).toBeInTheDocument();
  });

  it("avisa quando não há nada salvo", async () => {
    mockFetch([]);

    render(<SavedAddresses token="t" />);

    expect(
      await screen.findByText("Nenhum endereço salvo ainda."),
    ).toBeInTheDocument();
  });

  it("exclui depois de confirmar, explicando o efeito", async () => {
    const fetchMock = mockFetch(ENTRIES);
    const confirmSpy = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirmSpy);

    render(<SavedAddresses token="t" />);
    await screen.findByText("Rua Osório, 250 - Centro");

    fetchMock.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
    await userEvent.click(
      screen.getByRole("button", { name: "Excluir Rua Osório, 250 - Centro" }),
    );

    expect(confirmSpy.mock.calls[0][0]).toContain(
      "localizado de novo na próxima rota",
    );
    await waitFor(() =>
      expect(screen.queryByText("Rua Osório, 250 - Centro")).not.toBeInTheDocument(),
    );

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(lastCall[0]).toContain("/api/geocode-cache/1");
    expect(lastCall[1].method).toBe("DELETE");
  });

  it("não exclui se ela cancelar a confirmação", async () => {
    const fetchMock = mockFetch(ENTRIES);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));

    render(<SavedAddresses token="t" />);
    await screen.findByText("Rua Osório, 250 - Centro");

    await userEvent.click(
      screen.getByRole("button", { name: "Excluir Rua Osório, 250 - Centro" }),
    );

    expect(fetchMock).toHaveBeenCalledTimes(1); // só o GET inicial
    expect(screen.getByText("Rua Osório, 250 - Centro")).toBeInTheDocument();
  });

  it("abre o mapa no ponto atual ao corrigir", async () => {
    mockFetch(ENTRIES);

    render(<SavedAddresses token="t" />);
    await screen.findByText("Rua Osório, 250 - Centro");

    await userEvent.click(screen.getAllByRole("button", { name: "Corrigir" })[0]);

    expect(screen.getByTestId("pin-map")).toHaveTextContent("-12.73");
    expect(
      screen.getByText("Corrigindo: Rua Osório, 250 - Centro"),
    ).toBeInTheDocument();
  });

  it("salva a correção com PATCH e atualiza a lista", async () => {
    const fetchMock = mockFetch(ENTRIES);

    render(<SavedAddresses token="t" />);
    await screen.findByText("Rua Osório, 250 - Centro");
    await userEvent.click(screen.getAllByRole("button", { name: "Corrigir" })[0]);

    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...ENTRIES[0], latitude: -12.8, source: "manual" }),
    });
    await userEvent.click(screen.getByRole("button", { name: "Salvar correção" }));

    await waitFor(() =>
      expect(screen.queryByTestId("pin-map")).not.toBeInTheDocument(),
    );

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(lastCall[0]).toContain("/api/geocode-cache/1");
    expect(lastCall[1].method).toBe("PATCH");
    expect(JSON.parse(lastCall[1].body)).toEqual({
      latitude: -12.73,
      longitude: -60.14,
    });
  });

  it("mostra só a mensagem humana quando a API recusa", async () => {
    mockFetch({ detail: "Endereço salvo não encontrado" }, false, 404);

    render(<SavedAddresses token="t" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Endereço salvo não encontrado");
    expect(alert.textContent).not.toMatch(/404|fetch/i);
  });
});
