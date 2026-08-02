export interface DeliveryInput {
  address: string;
  latitude: number;
  longitude: number;
  jet_order_id?: string | null;
}

export interface Delivery extends DeliveryInput {
  id: number;
  route_id: number;
  sequence_order: number | null;
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
