"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  correctSavedAddress,
  deleteSavedAddress,
  listSavedAddresses,
} from "@/lib/api";
import type { Coordinates, SavedAddress } from "@/lib/types";

// Leaflet depende de window — sem ssr:false o build da Vercel quebra.
const PinMap = dynamic(() => import("@/components/PinMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-80 items-center justify-center rounded-md bg-gray-100 text-gray-500">
      Carregando mapa...
    </div>
  ),
});

function formatDate(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleDateString("pt-BR");
}

/**
 * Endereços que o app já guardou. Um pin confirmado por engano fica salvo para
 * sempre — é aqui que ela conserta ou apaga.
 */
export default function SavedAddresses({ token }: { token: string }) {
  const [addresses, setAddresses] = useState<SavedAddress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [correcting, setCorrecting] = useState<SavedAddress | null>(null);
  const [position, setPosition] = useState<Coordinates | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setAddresses(await listSavedAddresses(token));
      setError("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Erro ao carregar endereços salvos",
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const startCorrection = (entry: SavedAddress) => {
    setCorrecting(entry);
    setPosition({ latitude: entry.latitude, longitude: entry.longitude });
    setError("");
  };

  const handleDelete = async (entry: SavedAddress) => {
    const confirmed = window.confirm(
      "Remover este endereço salvo? Ele será localizado de novo na próxima rota.",
    );
    if (!confirmed) return;

    try {
      await deleteSavedAddress(entry.id, token);
      setAddresses((current) => current.filter((item) => item.id !== entry.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao remover");
    }
  };

  const handleSaveCorrection = async () => {
    if (!correcting || !position) return;

    setSaving(true);
    try {
      const updated = await correctSavedAddress(
        correcting.id,
        position.latitude,
        position.longitude,
        token,
      );
      setAddresses((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setCorrecting(null);
      setPosition(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao corrigir");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-1 text-xl font-bold">Endereços salvos</h2>
      <p className="mb-4 text-xs text-gray-500">
        O app reaproveita estes pontos nas próximas rotas. Corrija se algum
        estiver no lugar errado.
      </p>

      {loading && <p className="text-sm text-gray-500">Carregando...</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {!loading && !error && addresses.length === 0 && (
        <p className="text-sm text-gray-500">Nenhum endereço salvo ainda.</p>
      )}

      <ul className="max-h-72 space-y-2 overflow-y-auto">
        {addresses.map((entry) => (
          <li
            key={entry.id}
            className="rounded border border-gray-200 p-3 text-sm"
          >
            <p className="font-medium">{entry.address ?? entry.address_key}</p>
            <p className="text-xs text-gray-500">
              {entry.source === "manual" ? "Corrigido por você" : "Google"} ·{" "}
              {entry.latitude.toFixed(5)}, {entry.longitude.toFixed(5)}
              {entry.updated_at && ` · ${formatDate(entry.updated_at)}`}
            </p>

            <div className="mt-2 flex gap-3">
              <button
                onClick={() => startCorrection(entry)}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                Corrigir
              </button>
              <button
                onClick={() => handleDelete(entry)}
                aria-label={`Excluir ${entry.address ?? entry.address_key}`}
                className="text-sm text-red-600 hover:text-red-800"
              >
                Excluir
              </button>
            </div>
          </li>
        ))}
      </ul>

      {correcting && position && (
        <div className="mt-4 space-y-2 rounded border-2 border-blue-300 p-3">
          <p className="text-sm font-medium">
            Corrigindo: {correcting.address ?? correcting.address_key}
          </p>
          <PinMap position={position} onMove={setPosition} />
          <p className="text-xs text-gray-500">
            Arraste o pin ou toque no mapa para ajustar.
          </p>
          <div className="flex gap-2">
            <Button
              onClick={handleSaveCorrection}
              disabled={saving}
              className="flex-1"
            >
              {saving ? "Salvando..." : "Salvar correção"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setCorrecting(null);
                setPosition(null);
              }}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
