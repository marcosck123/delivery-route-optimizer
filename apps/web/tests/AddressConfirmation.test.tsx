import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AddressConfirmation from "@/components/AddressConfirmation";
import type { Delivery, GeocodeStatus } from "@/lib/types";

// O mapa Leaflet não roda em jsdom; aqui interessa o fluxo de confirmação.
vi.mock("@/components/PinMap", () => ({
  default: ({ position }: { position: { latitude: number } }) => (
    <div data-testid="pin-map">pin em {position.latitude}</div>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function delivery(
  id: number,
  status: GeocodeStatus,
  overrides: Partial<Delivery> = {},
): Delivery {
  return {
    id,
    route_id: 1,
    address: `Rua ${id}, ${id}0 - Centro`,
    street: `Rua ${id}`,
    number: `${id}0`,
    neighborhood: "Centro",
    cep: null,
    complement: null,
    latitude: -12.74,
    longitude: -60.14,
    geocode_status: status,
    geocode_source: "google",
    geocode_message: null,
    geocode_alternatives: null,
    sequence_order: null,
    ...overrides,
  };
}

function mockConfirm(response: Partial<Delivery> = {}) {
  const fetchMock = vi.fn().mockImplementation(async (_url, options) => {
    const body = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        ...delivery(body.delivery_id, "confirmed"),
        ...response,
      }),
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AddressConfirmation", () => {
  it("mostra o endereço atual e o progresso", () => {
    render(
      <AddressConfirmation
        routeId={1}
        deliveries={[delivery(1, "resolved"), delivery(2, "resolved")]}
        token="t"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={vi.fn()}
      />,
    );

    expect(screen.getByText("Rua 1, 10 - Centro")).toBeInTheDocument();
    expect(screen.getByText("1 de 2")).toBeInTheDocument();
    expect(screen.getByText("Encontrado ✓ — É esse mesmo?")).toBeInTheDocument();
  });

  it("avança para o próximo ao confirmar", async () => {
    const deliveries = [delivery(1, "resolved"), delivery(2, "resolved")];
    const onDeliveryConfirmed = vi.fn();
    mockConfirm();

    const { rerender } = render(
      <AddressConfirmation
        routeId={1}
        deliveries={deliveries}
        token="t"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={onDeliveryConfirmed}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Sim, próximo" }));
    await waitFor(() => expect(onDeliveryConfirmed).toHaveBeenCalled());

    // o pai troca o item confirmado e o componente puxa o próximo sozinho
    rerender(
      <AddressConfirmation
        routeId={1}
        deliveries={[delivery(1, "confirmed"), delivery(2, "resolved")]}
        token="t"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={onDeliveryConfirmed}
      />,
    );

    expect(screen.getByText("Rua 2, 20 - Centro")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
  });

  it("avisa quando termina a lista", async () => {
    const onAllConfirmed = vi.fn();
    mockConfirm();

    render(
      <AddressConfirmation
        routeId={1}
        deliveries={[delivery(1, "resolved")]}
        token="t"
        onAllConfirmed={onAllConfirmed}
        onDeliveryConfirmed={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Sim, próximo" }));
    await waitFor(() => expect(onAllConfirmed).toHaveBeenCalled());
  });

  it("envia as coordenadas do pin para o endpoint certo", async () => {
    const fetchMock = mockConfirm();

    render(
      <AddressConfirmation
        routeId={9}
        deliveries={[delivery(4, "resolved", { latitude: -12.5, longitude: -60.5 })]}
        token="meu-token"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Sim, próximo" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/routes/9/deliveries/4/confirm-pin");
    expect(options.headers.Authorization).toBe("Bearer meu-token");
    expect(JSON.parse(options.body)).toEqual({
      delivery_id: 4,
      latitude: -12.5,
      longitude: -60.5,
    });
  });

  it("mostra a mensagem humana de um endereço que precisa de conferência", () => {
    render(
      <AddressConfirmation
        routeId={1}
        deliveries={[
          delivery(1, "needs_confirmation", {
            geocode_message: "Dois resultados diferentes — confirme no mapa",
            geocode_alternatives: [
              { latitude: -12.74, longitude: -60.14 },
              { latitude: -12.75, longitude: -60.15 },
            ],
          }),
        ]}
        token="t"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Dois resultados diferentes — confirme no mapa",
    );
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeInTheDocument();
  });

  it("cai no centro da cidade quando não há coordenada nenhuma", () => {
    render(
      <AddressConfirmation
        routeId={1}
        deliveries={[
          delivery(1, "failed", {
            latitude: null,
            longitude: null,
            geocode_message: "Rua não encontrada",
          }),
        ]}
        token="t"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Rua não encontrada");
    expect(screen.getByTestId("pin-map")).toHaveTextContent("-12.7406");
  });

  it("mostra só a mensagem humana quando salvar falha", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: "Não foi possível salvar o ponto" }),
      }),
    );

    render(
      <AddressConfirmation
        routeId={1}
        deliveries={[delivery(1, "resolved")]}
        token="t"
        onAllConfirmed={vi.fn()}
        onDeliveryConfirmed={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Sim, próximo" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível salvar o ponto");
    expect(alert.textContent).not.toMatch(/500|fetch|http/i);
  });
});
