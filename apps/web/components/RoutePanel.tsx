"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  getRoute,
  optimizeRoute,
  syncJetOrders,
  uploadCsv,
} from "@/lib/api";
import { formatKm, routeDistanceKm, sortDeliveries } from "@/lib/route";
import type { Route } from "@/lib/types";

// Leaflet depende de window — só carrega no cliente.
const RouteMap = dynamic(() => import("@/components/RouteMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[500px] items-center justify-center text-gray-500">
      Carregando mapa...
    </div>
  ),
});

export default function RoutePanel({
  routeId,
  token,
  onRouteChanged,
}: {
  routeId: number;
  token: string;
  onRouteChanged: () => void;
}) {
  const [route, setRoute] = useState<Route | null>(null);
  const [busy, setBusy] = useState<"load" | "optimize" | "jet" | "csv" | null>(
    "load",
  );
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setBusy("load");
    try {
      setRoute(await getRoute(routeId, token));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar a rota");
    } finally {
      setBusy(null);
    }
  }, [routeId, token]);

  useEffect(() => {
    load();
  }, [load]);

  const runAction = async (
    action: "optimize" | "jet",
    request: () => Promise<Route>,
  ) => {
    setBusy(action);
    setError("");
    try {
      setRoute(await request());
      onRouteChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro na operação");
    } finally {
      setBusy(null);
    }
  };

  const handleCsvUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setBusy("csv");
    setError("");
    try {
      await uploadCsv(routeId, file, token);
      setRoute(await getRoute(routeId, token));
      onRouteChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao importar CSV");
    } finally {
      setBusy(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const distance = route ? routeDistanceKm(route) : null;
  const osrmError = route?.optimization_result?.osrm?.error;

  return (
    <section className="overflow-hidden rounded-lg bg-white shadow">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
        <div>
          <h2 className="text-xl font-bold">{route?.name ?? "Rota"}</h2>
          <p className="text-sm text-gray-500">
            {route ? `${route.deliveries.length} entrega(s)` : "Carregando..."}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <label className="cursor-pointer rounded-md bg-gray-200 px-4 py-2 font-medium text-gray-900 hover:bg-gray-300">
            {busy === "csv" ? "Importando..." : "Importar CSV"}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={handleCsvUpload}
              className="hidden"
            />
          </label>
          <Button
            variant="secondary"
            disabled={busy !== null}
            onClick={() => runAction("jet", () => syncJetOrders(routeId, token))}
          >
            {busy === "jet" ? "Sincronizando..." : "Sincronizar J&T"}
          </Button>
          <Button
            disabled={busy !== null || !route?.deliveries.length}
            onClick={() =>
              runAction("optimize", () => optimizeRoute(routeId, token))
            }
          >
            {busy === "optimize" ? "Otimizando..." : "Otimizar Rota"}
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="border-b bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <RouteMap route={route} />

      {distance && (
        <div className="border-t bg-green-50 p-4 text-sm text-green-800">
          ✓ Rota otimizada · distância total: {formatKm(distance.km)}
          {distance.source === "estimate" && " (estimativa em linha reta)"}
          {osrmError && (
            <span className="ml-1 text-green-900/70">— OSRM: {osrmError}</span>
          )}
        </div>
      )}

      {route && route.deliveries.length > 0 && (
        <ol className="max-h-64 divide-y overflow-y-auto">
          {sortDeliveries(route.deliveries).map((delivery, index) => (
            <li key={delivery.id} className="flex gap-3 p-3 text-sm">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate">{delivery.address}</span>
                {delivery.jet_order_id && (
                  <span className="text-xs text-gray-500">
                    Pedido J&T: {delivery.jet_order_id}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
