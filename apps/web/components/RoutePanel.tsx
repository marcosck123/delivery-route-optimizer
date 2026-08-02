"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AddressConfirmation from "@/components/AddressConfirmation";
import { Button } from "@/components/ui/Button";
import {
  geocodeRoute,
  getRoute,
  optimizeRoute,
  syncJetOrders,
  uploadCsv,
} from "@/lib/api";
import { formatKm, routeDistanceKm, sortDeliveries } from "@/lib/route";
import { isReady, type Delivery, type Route } from "@/lib/types";

// Leaflet depende de window — só carrega no cliente.
const RouteMap = dynamic(() => import("@/components/RouteMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[500px] items-center justify-center text-gray-500">
      Carregando mapa...
    </div>
  ),
});

type Busy = "load" | "optimize" | "jet" | "csv" | "geocode" | null;

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
  const [busy, setBusy] = useState<Busy>("load");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const autoGeocodedRef = useRef<number | null>(null);

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
    autoGeocodedRef.current = null;
    load();
  }, [load]);

  const deliveries = useMemo(() => route?.deliveries ?? [], [route]);
  const pendingGeocode = deliveries.filter((d) => d.geocode_status === "pending");
  const unconfirmed = deliveries.filter((d) => d.geocode_status !== "confirmed");
  const allReady = deliveries.length > 0 && deliveries.every(isReady);

  const runGeocode = useCallback(async () => {
    setBusy("geocode");
    setError("");
    try {
      const updated = await geocodeRoute(routeId, token);
      setRoute((current) =>
        current ? { ...current, deliveries: updated } : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao buscar endereços");
    } finally {
      setBusy(null);
    }
  }, [routeId, token]);

  // Assim que a rota carrega com endereços pendentes, busca sozinho.
  useEffect(() => {
    if (
      busy === null &&
      pendingGeocode.length > 0 &&
      autoGeocodedRef.current !== routeId
    ) {
      autoGeocodedRef.current = routeId;
      runGeocode();
    }
  }, [busy, pendingGeocode.length, routeId, runGeocode]);

  const replaceDelivery = (updated: Delivery) => {
    setRoute((current) =>
      current
        ? {
            ...current,
            deliveries: current.deliveries.map((delivery) =>
              delivery.id === updated.id ? updated : delivery,
            ),
          }
        : current,
    );
  };

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
      autoGeocodedRef.current = null;
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
    <div className="space-y-4">
      <section className="overflow-hidden rounded-lg bg-white shadow">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <div>
            <h2 className="text-xl font-bold">{route?.name ?? "Rota"}</h2>
            <p className="text-sm text-gray-500">
              {route
                ? `${deliveries.length} endereço(s)${
                    unconfirmed.length > 0
                      ? ` · ${unconfirmed.length} a confirmar`
                      : ""
                  }`
                : "Carregando..."}
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
              disabled={busy !== null || pendingGeocode.length === 0}
              onClick={runGeocode}
            >
              {busy === "geocode" ? "Buscando..." : "Buscar endereços"}
            </Button>
            <Button
              variant="secondary"
              disabled={busy !== null}
              onClick={() => runAction("jet", () => syncJetOrders(routeId, token))}
            >
              {busy === "jet" ? "Sincronizando..." : "Sincronizar J&T"}
            </Button>
            <Button
              disabled={busy !== null || !allReady}
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

        {deliveries.length > 0 && (
          <ol className="max-h-64 divide-y overflow-y-auto">
            {sortDeliveries(deliveries).map((delivery, index) => (
              <li key={delivery.id} className="flex gap-3 p-3 text-sm">
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${
                    isReady(delivery) ? "bg-blue-600" : "bg-gray-400"
                  }`}
                >
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{delivery.address}</span>
                  {delivery.geocode_message && (
                    <span className="text-xs text-amber-700">
                      {delivery.geocode_message}
                    </span>
                  )}
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

      {unconfirmed.length > 0 && busy !== "geocode" && (
        <AddressConfirmation
          routeId={routeId}
          deliveries={deliveries}
          token={token}
          onDeliveryConfirmed={replaceDelivery}
          onAllConfirmed={onRouteChanged}
        />
      )}
    </div>
  );
}
