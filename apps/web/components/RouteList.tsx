"use client";

import { useCallback, useEffect, useState } from "react";

import { deleteRoute, listRoutes } from "@/lib/api";
import type { RouteSummary } from "@/lib/types";

export default function RouteList({
  token,
  version,
  selectedRouteId,
  onSelect,
  onDeleted,
}: {
  token: string;
  version: number;
  selectedRouteId: number | null;
  onSelect: (routeId: number) => void;
  onDeleted: (routeId: number) => void;
}) {
  const [routes, setRoutes] = useState<RouteSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRoutes(await listRoutes(token));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar rotas");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load, version]);

  const handleDelete = async (routeId: number) => {
    if (!window.confirm("Excluir esta rota?")) return;
    try {
      await deleteRoute(routeId, token);
      setRoutes((current) => current.filter((route) => route.id !== routeId));
      onDeleted(routeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir rota");
    }
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-4 text-xl font-bold">Histórico de Rotas</h2>

      {loading && <p className="text-sm text-gray-500">Carregando...</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!loading && !error && routes.length === 0 && (
        <p className="text-sm text-gray-500">Nenhuma rota criada ainda.</p>
      )}

      <ul className="max-h-72 space-y-2 overflow-y-auto">
        {routes.map((route) => (
          <li key={route.id}>
            <div
              className={`flex items-center justify-between gap-2 rounded border p-3 ${
                route.id === selectedRouteId
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200"
              }`}
            >
              <button
                onClick={() => onSelect(route.id)}
                className="min-w-0 flex-1 text-left"
              >
                <span className="block truncate font-medium">{route.name}</span>
                <span className="block text-xs text-gray-500">
                  {new Date(route.created_at).toLocaleString("pt-BR")} ·{" "}
                  {route.delivery_count} entrega(s)
                </span>
              </button>
              <button
                onClick={() => handleDelete(route.id)}
                aria-label={`Excluir rota ${route.name}`}
                className="shrink-0 text-sm text-red-600 hover:text-red-800"
              >
                Excluir
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
