"use client";

import { useCallback, useEffect, useState } from "react";

import JetConfigPanel from "@/components/JetConfigPanel";
import Login from "@/components/Login";
import RouteForm from "@/components/RouteForm";
import RouteList from "@/components/RouteList";
import RoutePanel from "@/components/RoutePanel";
import SavedAddresses from "@/components/SavedAddresses";
import { TOKEN_STORAGE_KEY } from "@/lib/api";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(null);
  const [routesVersion, setRoutesVersion] = useState(0);

  useEffect(() => {
    setToken(localStorage.getItem(TOKEN_STORAGE_KEY));
    setReady(true);
  }, []);

  const handleLoginSuccess = useCallback((newToken: string) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
    setToken(newToken);
  }, []);

  const handleLogout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setSelectedRouteId(null);
  }, []);

  const refreshRoutes = useCallback(() => {
    setRoutesVersion((version) => version + 1);
  }, []);

  // enquanto o token não é lido do localStorage, evita piscar a tela de login
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 text-gray-500">
        Carregando...
      </div>
    );
  }

  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Delivery Route Optimizer
            </h1>
            <p className="mt-1 text-gray-600">
              Defina as entregas e otimize a rota automaticamente
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="rounded-md bg-red-600 px-4 py-2 text-white hover:bg-red-700"
          >
            Sair
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div className="space-y-8">
            <RouteForm
              token={token}
              onRouteCreated={(routeId) => {
                setSelectedRouteId(routeId);
                refreshRoutes();
              }}
            />
            <RouteList
              token={token}
              version={routesVersion}
              selectedRouteId={selectedRouteId}
              onSelect={setSelectedRouteId}
              onDeleted={(routeId) => {
                if (routeId === selectedRouteId) setSelectedRouteId(null);
                refreshRoutes();
              }}
            />
            <SavedAddresses token={token} />
            <JetConfigPanel token={token} />
          </div>

          <div className="lg:col-span-2">
            {selectedRouteId ? (
              <RoutePanel
                routeId={selectedRouteId}
                token={token}
                onRouteChanged={refreshRoutes}
              />
            ) : (
              <div className="flex h-96 items-center justify-center rounded-lg bg-white p-8 text-center text-gray-500 shadow">
                Crie uma rota ou selecione uma do histórico para ver o mapa.
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
