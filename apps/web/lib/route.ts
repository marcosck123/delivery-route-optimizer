import type { Delivery, Route } from "./types";

/** Entregas na ordem otimizada; as sem ordem definida vão para o fim. */
export function sortDeliveries(deliveries: Delivery[]): Delivery[] {
  return [...deliveries].sort((a, b) => {
    const aOrder = a.sequence_order ?? Number.MAX_SAFE_INTEGER;
    const bOrder = b.sequence_order ?? Number.MAX_SAFE_INTEGER;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return a.id - b.id;
  });
}

/**
 * Distância da rota em km: usa a malha viária do OSRM quando disponível e
 * cai para a estimativa em linha reta quando o OSRM falhou.
 */
export function routeDistanceKm(
  route: Route,
): { km: number; source: "osrm" | "estimate" } | null {
  const result = route.optimization_result;
  if (!result) return null;

  const osrmDistance = result.osrm?.routes?.[0]?.distance;
  if (typeof osrmDistance === "number") {
    return { km: osrmDistance / 1000, source: "osrm" };
  }
  if (typeof result.estimated_distance_km === "number") {
    return { km: result.estimated_distance_km, source: "estimate" };
  }
  return null;
}

export function formatKm(km: number): string {
  return `${km.toFixed(1).replace(".", ",")} km`;
}
