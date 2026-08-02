import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import StartPointPanel from "@/components/StartPointPanel";
import type { Route } from "@/lib/types";

// O mapa Leaflet não roda em jsdom; aqui interessa o fluxo do painel.
vi.mock("@/components/PinMap", () => ({
  default: ({ position }: { position: { latitude: number } }) => (
    <div data-testid="pin-map">pin em {position.latitude}</div>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function route(overrides: Partial<Route> = {}): Route {
  return {
    id: 7,
    name: "Rota",
    created_at: "2026-08-02T12:00:00Z",
    deliveries: [],
    optimization_result: null,
    start_latitude: null,
    start_longitude: null,
    start_address: null,
    ...overrides,
  };
}

function mockJson(response: unknown, ok = true, status = 200) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok, status, json: async () => response });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function fillStartAddress() {
  await userEvent.type(screen.getByLabelText("Rua (partida)"), "Rua da Partida");
  await userEvent.type(screen.getByLabelText("Número (partida)"), "10");
  await userEvent.type(screen.getByLabelText("Bairro (partida)"), "Centro");
}

describe("StartPointPanel", () => {
  it("deixa claro que o ponto de partida é opcional", () => {
    render(<StartPointPanel route={route()} token="t" onChanged={vi.fn()} />);

    expect(
      screen.getByText(/Sem ele, a rota começa pela primeira entrega/),
    ).toBeInTheDocument();
  });

  it("exige rua, número e bairro", async () => {
    render(<StartPointPanel route={route()} token="t" onChanged={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Rua (partida)"), "Rua A");
    await userEvent.click(screen.getByRole("button", { name: "Definir partida" }));

    expect(screen.getByRole("status")).toHaveTextContent("Preencha: número, bairro");
  });

  it("salva quando o endereço resolve direto", async () => {
    const fetchMock = mockJson({
      saved: true,
      latitude: -12.73,
      longitude: -60.14,
      address: "Rua da Partida, 10 - Centro",
      status: "resolved",
      source: "google",
      message: null,
      alternatives: [],
    });
    const onChanged = vi.fn();

    render(<StartPointPanel route={route()} token="tok" onChanged={onChanged} />);
    await fillStartAddress();
    await userEvent.click(screen.getByRole("button", { name: "Definir partida" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/routes/7/start-point");
    expect(JSON.parse(options.body)).toMatchObject({
      street: "Rua da Partida",
      number: "10",
      neighborhood: "Centro",
    });
  });

  it("abre o mapa para confirmar quando o endereço é ambíguo", async () => {
    mockJson({
      saved: false,
      latitude: -12.73,
      longitude: -60.14,
      address: "Rua Duvidosa, 1 - Centro",
      status: "needs_confirmation",
      source: "google",
      message: "Endereço aproximado — confirme no mapa",
      alternatives: [],
    });

    render(<StartPointPanel route={route()} token="t" onChanged={vi.fn()} />);
    await fillStartAddress();
    await userEvent.click(screen.getByRole("button", { name: "Definir partida" }));

    expect(await screen.findByTestId("pin-map")).toHaveTextContent("-12.73");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Endereço aproximado — confirme no mapa",
    );
    expect(
      screen.getByRole("button", { name: "Confirmar partida" }),
    ).toBeInTheDocument();
  });

  it("confirma o pin enviando as coordenadas", async () => {
    const fetchMock = mockJson({
      saved: false,
      latitude: -12.73,
      longitude: -60.14,
      address: null,
      status: "needs_confirmation",
      source: null,
      message: "Confirme no mapa",
      alternatives: [],
    });

    render(<StartPointPanel route={route()} token="t" onChanged={vi.fn()} />);
    await fillStartAddress();
    await userEvent.click(screen.getByRole("button", { name: "Definir partida" }));
    await screen.findByTestId("pin-map");

    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        saved: true,
        latitude: -12.73,
        longitude: -60.14,
        address: "Rua da Partida, 10 - Centro",
        status: "confirmed",
        source: "manual",
        message: null,
        alternatives: [],
      }),
    });
    await userEvent.click(screen.getByRole("button", { name: "Confirmar partida" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
      latitude: -12.73,
      longitude: -60.14,
    });
  });

  it("mostra o ponto já definido com o selo de início", () => {
    render(
      <StartPointPanel
        route={route({
          start_latitude: -12.75,
          start_longitude: -60.15,
          start_address: "Minha casa",
        })}
        token="t"
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByText("Início")).toBeInTheDocument();
    expect(screen.getByText("Minha casa")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Alterar" })).toBeInTheDocument();
  });

  it("remove o ponto de partida", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();

    render(
      <StartPointPanel
        route={route({
          start_latitude: -12.75,
          start_longitude: -60.15,
          start_address: "Minha casa",
        })}
        token="t"
        onChanged={onChanged}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Remover" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });

  it("usa a localização atual do aparelho", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: {
        getCurrentPosition: (success: PositionCallback) =>
          success({
            coords: { latitude: -12.8, longitude: -60.2 },
          } as GeolocationPosition),
      },
    });

    render(<StartPointPanel route={route()} token="t" onChanged={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Usar minha localização" }),
    );

    expect(await screen.findByTestId("pin-map")).toHaveTextContent("-12.8");
  });

  it("avisa quando a localização falha, sem erro técnico", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: {
        getCurrentPosition: (
          _success: PositionCallback,
          failure: PositionErrorCallback,
        ) => failure({ code: 1, message: "User denied" } as GeolocationPositionError),
      },
    });

    render(<StartPointPanel route={route()} token="t" onChanged={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Usar minha localização" }),
    );

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Não consegui pegar sua localização");
    expect(status.textContent).not.toMatch(/denied|code/i);
  });
});
