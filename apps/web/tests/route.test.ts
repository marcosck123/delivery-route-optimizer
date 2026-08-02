import { describe, expect, it } from "vitest";

import { formatKm, routeDistanceKm, sortDeliveries } from "@/lib/route";
import type { Delivery, Route } from "@/lib/types";

function delivery(id: number, sequenceOrder: number | null): Delivery {
  return {
    id,
    route_id: 1,
    address: `Rua ${id}`,
    street: `Rua ${id}`,
    number: "10",
    neighborhood: "Centro",
    cep: null,
    complement: null,
    latitude: -12.74,
    longitude: -60.14,
    geocode_status: "confirmed",
    geocode_source: "manual",
    geocode_message: null,
    geocode_alternatives: null,
    sequence_order: sequenceOrder,
  };
}

function route(optimizationResult: Route["optimization_result"]): Route {
  return {
    id: 1,
    name: "Rota",
    created_at: "2026-08-01T12:00:00Z",
    deliveries: [],
    optimization_result: optimizationResult,
    start_latitude: null,
    start_longitude: null,
    start_address: null,
  };
}

describe("sortDeliveries", () => {
  it("ordena pela sequência otimizada", () => {
    const sorted = sortDeliveries([delivery(1, 2), delivery(2, 0), delivery(3, 1)]);
    expect(sorted.map((d) => d.id)).toEqual([2, 3, 1]);
  });

  it("joga entregas sem ordem para o fim, mantendo o id como desempate", () => {
    const sorted = sortDeliveries([delivery(5, null), delivery(2, null), delivery(9, 0)]);
    expect(sorted.map((d) => d.id)).toEqual([9, 2, 5]);
  });

  it("não muta o array original", () => {
    const original = [delivery(1, 1), delivery(2, 0)];
    sortDeliveries(original);
    expect(original.map((d) => d.id)).toEqual([1, 2]);
  });
});

describe("routeDistanceKm", () => {
  it("devolve null sem otimização", () => {
    expect(routeDistanceKm(route(null))).toBeNull();
  });

  it("prefere a distância do OSRM", () => {
    const result = routeDistanceKm(
      route({
        optimized_order: [1, 2],
        estimated_distance_km: 3,
        start_point: null,
        osrm: { routes: [{ distance: 4321 }] },
      }),
    );
    expect(result).toEqual({ km: 4.321, source: "osrm" });
  });

  it("cai para a estimativa quando o OSRM falhou", () => {
    const result = routeDistanceKm(
      route({
        optimized_order: [1, 2],
        estimated_distance_km: 3.5,
        start_point: null,
        osrm: { error: "timeout" },
      }),
    );
    expect(result).toEqual({ km: 3.5, source: "estimate" });
  });
});

describe("formatKm", () => {
  it("formata no padrão pt-BR", () => {
    expect(formatKm(4.321)).toBe("4,3 km");
  });
});
