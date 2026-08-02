export type GeocodeStatus =
  | "pending"
  | "resolved"
  | "needs_confirmation"
  | "failed"
  | "confirmed";

/** Address typed by the user. Coordinates come from geocoding. */
export interface AddressInput {
  street: string;
  number: string;
  neighborhood: string;
  cep?: string | null;
  complement?: string | null;
}

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface Delivery extends AddressInput {
  id: number;
  route_id: number;
  address: string;
  latitude: number | null;
  longitude: number | null;
  geocode_status: GeocodeStatus;
  geocode_source: string | null;
  geocode_message: string | null;
  geocode_alternatives: Coordinates[] | null;
  sequence_order: number | null;
  jet_order_id?: string | null;
}

export interface OsrmRoute {
  distance?: number;
  duration?: number;
  geometry?: { type: string; coordinates: [number, number][] };
}

export interface OsrmResult {
  routes?: OsrmRoute[];
  error?: string;
}

export interface OptimizationResult {
  optimized_order: number[];
  estimated_distance_km: number;
  osrm: OsrmResult;
}

export interface Route {
  id: number;
  name: string;
  created_at: string;
  deliveries: Delivery[];
  optimization_result: OptimizationResult | null;
}

export interface RouteSummary {
  id: number;
  name: string;
  created_at: string;
  delivery_count: number;
}

export interface JetConfig {
  id: number;
  jet_username: string;
  created_at: string;
}

/** Coordinates are trustworthy only in these two states. */
export const READY_STATUSES: GeocodeStatus[] = ["resolved", "confirmed"];

export function isReady(delivery: Delivery): boolean {
  return (
    delivery.latitude !== null &&
    delivery.longitude !== null &&
    READY_STATUSES.includes(delivery.geocode_status)
  );
}
