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
  start_point: (Coordinates & { address: string | null }) | null;
  osrm: OsrmResult;
}

export interface Route {
  id: number;
  name: string;
  created_at: string;
  deliveries: Delivery[];
  optimization_result: OptimizationResult | null;
  /** Ponto de partida opcional: de onde o trajeto começa. */
  start_latitude: number | null;
  start_longitude: number | null;
  start_address: string | null;
}

export interface StartPointInput {
  street?: string;
  number?: string;
  neighborhood?: string;
  cep?: string | null;
  complement?: string | null;
  latitude?: number;
  longitude?: number;
  address?: string;
}

export interface StartPointResponse {
  /** false = ainda precisa da confirmação dela no mapa. */
  saved: boolean;
  latitude: number | null;
  longitude: number | null;
  address: string | null;
  status: GeocodeStatus;
  source: string | null;
  message: string | null;
  alternatives: Coordinates[];
}

export interface RouteSummary {
  id: number;
  name: string;
  created_at: string;
  delivery_count: number;
}

/** One delivery read from a photo, before the user reviews it. */
export interface OcrBlock {
  raw_text: string;
  /** Número do pedido lido da tela; vira jet_order_id na entrega. */
  order_id: string | null;
  street: string | null;
  number: string | null;
  neighborhood: string | null;
  complement: string | null;
  cep: string | null;
}

export interface OcrUploadResponse {
  blocks: OcrBlock[];
  message: string;
}

/** Um endereço salvo no cache de geocoding. */
export interface SavedAddress {
  id: number;
  address: string | null;
  address_key: string;
  latitude: number;
  longitude: number;
  source: string; // google | manual
  created_at: string | null;
  updated_at: string | null;
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
