import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RouteForm from "@/components/RouteForm";

afterEach(() => {
  vi.restoreAllMocks();
});

async function addDelivery(address: string, lat: string, lon: string) {
  await userEvent.type(screen.getByLabelText("Endereço"), address);
  await userEvent.type(screen.getByLabelText("Latitude"), lat);
  await userEvent.type(screen.getByLabelText("Longitude"), lon);
  await userEvent.click(screen.getByRole("button", { name: "+ Adicionar" }));
}

describe("RouteForm", () => {
  it("adiciona e remove entregas da lista", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await addDelivery("Rua A, 10", "-12.7406", "-60.1458");
    expect(screen.getByText("Entregas (1)")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remover" }));
    expect(screen.queryByText("Entregas (1)")).not.toBeInTheDocument();
  });

  it("exige nome da rota antes de criar", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await addDelivery("Rua A, 10", "-12.7406", "-60.1458");
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    expect(screen.getByRole("status")).toHaveTextContent("Dê um nome para a rota");
  });

  it("exige pelo menos uma entrega", async () => {
    render(<RouteForm token="t" onRouteCreated={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Nome da Rota"), "Rota 1");
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Adicione pelo menos uma entrega",
    );
  });

  it("cria a rota com token e entregas", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 7, name: "Rota 1" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onRouteCreated = vi.fn();

    render(<RouteForm token="meu-token" onRouteCreated={onRouteCreated} />);

    await userEvent.type(screen.getByLabelText("Nome da Rota"), "Rota 1");
    await addDelivery("Rua A, 10", "-12.7406", "-60.1458");
    await userEvent.click(screen.getByRole("button", { name: "Criar Rota" }));

    await waitFor(() => expect(onRouteCreated).toHaveBeenCalledWith(7));

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/routes/");
    expect(options.headers.Authorization).toBe("Bearer meu-token");
    expect(JSON.parse(options.body)).toEqual({
      name: "Rota 1",
      deliveries: [
        { address: "Rua A, 10", latitude: -12.7406, longitude: -60.1458 },
      ],
    });
  });
});
