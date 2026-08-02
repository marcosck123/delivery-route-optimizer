"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { clearStartPoint, setStartPoint } from "@/lib/api";
import { CITY_CENTER } from "@/lib/geo";
import type { Coordinates, Route, StartPointResponse } from "@/lib/types";

// Leaflet depende de window — sem ssr:false o build da Vercel quebra.
const PinMap = dynamic(() => import("@/components/PinMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-80 items-center justify-center rounded-md bg-gray-100 text-gray-500">
      Carregando mapa...
    </div>
  ),
});

const EMPTY_FORM = {
  street: "",
  number: "",
  neighborhood: "",
  complement: "",
  cep: "",
};

/**
 * Define de onde a rota começa. É opcional: sem ponto de partida, a rota
 * começa pela primeira entrega, como antes.
 */
export default function StartPointPanel({
  route,
  token,
  onChanged,
}: {
  route: Route;
  token: string;
  onChanged: () => void;
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  // ponto aguardando confirmação no mapa (endereço ambíguo ou ajuste manual)
  const [pending, setPending] = useState<{
    position: Coordinates;
    alternatives: Coordinates[];
  } | null>(null);

  const hasStart = route.start_latitude !== null && route.start_longitude !== null;

  const setField = (field: keyof typeof EMPTY_FORM) => (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => setForm((current) => ({ ...current, [field]: event.target.value }));

  const handleResponse = (response: StartPointResponse) => {
    if (response.saved) {
      setPending(null);
      setEditing(false);
      setForm(EMPTY_FORM);
      setMessage({ text: "Local de partida definido", error: false });
      onChanged();
      return;
    }

    // não foi gravado: ela confere no mapa antes
    setPending({
      position:
        response.latitude !== null && response.longitude !== null
          ? { latitude: response.latitude, longitude: response.longitude }
          : CITY_CENTER,
      alternatives: response.alternatives ?? [],
    });
    setMessage({
      text: response.message ?? "Confirme o ponto no mapa",
      error: true,
    });
  };

  const run = async (action: () => Promise<StartPointResponse>) => {
    setBusy(true);
    setMessage(null);
    try {
      handleResponse(await action());
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Erro ao salvar o ponto",
        error: true,
      });
    } finally {
      setBusy(false);
    }
  };

  const handleSearchAddress = () => {
    const missing = [
      form.street.trim() ? null : "rua",
      form.number.trim() ? null : "número",
      form.neighborhood.trim() ? null : "bairro",
    ].filter(Boolean);

    if (missing.length > 0) {
      setMessage({ text: `Preencha: ${missing.join(", ")}`, error: true });
      return;
    }

    run(() =>
      setStartPoint(
        route.id,
        {
          street: form.street.trim(),
          number: form.number.trim(),
          neighborhood: form.neighborhood.trim(),
          cep: form.cep.trim() || null,
          complement: form.complement.trim() || null,
        },
        token,
      ),
    );
  };

  const handleConfirmPin = () => {
    if (!pending) return;
    run(() =>
      setStartPoint(
        route.id,
        {
          latitude: pending.position.latitude,
          longitude: pending.position.longitude,
          street: form.street.trim() || undefined,
          number: form.number.trim() || undefined,
          neighborhood: form.neighborhood.trim() || undefined,
        },
        token,
      ),
    );
  };

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setMessage({
        text: "Seu navegador não permite usar a localização",
        error: true,
      });
      return;
    }

    setBusy(true);
    setMessage(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setBusy(false);
        setPending({
          position: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
          },
          alternatives: [],
        });
        setMessage({ text: "Confira o ponto no mapa e confirme", error: false });
      },
      () => {
        setBusy(false);
        setMessage({
          text: "Não consegui pegar sua localização",
          error: true,
        });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const handleClear = async () => {
    setBusy(true);
    try {
      await clearStartPoint(route.id, token);
      setPending(null);
      setEditing(false);
      setMessage({ text: "Local de partida removido", error: false });
      onChanged();
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Erro ao remover",
        error: true,
      });
    } finally {
      setBusy(false);
    }
  };

  const showForm = editing || (!hasStart && !pending);

  return (
    <section className="rounded-lg border-2 border-blue-200 bg-white p-4 shadow">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-bold">Local de partida</h3>
        {hasStart && !editing && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Alterar
            </Button>
            <Button variant="danger" disabled={busy} onClick={handleClear}>
              Remover
            </Button>
          </div>
        )}
      </div>

      {hasStart && !editing && !pending ? (
        <p className="text-sm text-gray-700">
          <span className="mr-2 inline-block rounded-full bg-green-600 px-2 py-0.5 text-xs font-bold text-white">
            Início
          </span>
          {route.start_address ?? "Ponto marcado no mapa"}
        </p>
      ) : (
        <p className="mb-3 text-xs text-gray-500">
          Opcional. Sem ele, a rota começa pela primeira entrega.
        </p>
      )}

      {showForm && (
        <div className="space-y-2">
          <Input label="Rua (partida)" value={form.street} onChange={setField("street")} />
          <div className="grid grid-cols-2 gap-2">
            <Input
              label="Número (partida)"
              value={form.number}
              onChange={setField("number")}
            />
            <Input
              label="Bairro (partida)"
              value={form.neighborhood}
              onChange={setField("neighborhood")}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleSearchAddress} disabled={busy} className="flex-1">
              {busy ? "Buscando..." : "Definir partida"}
            </Button>
            <Button
              variant="secondary"
              onClick={handleUseCurrentLocation}
              disabled={busy}
            >
              Usar minha localização
            </Button>
            {editing && (
              <Button variant="secondary" onClick={() => setEditing(false)}>
                Cancelar
              </Button>
            )}
          </div>
        </div>
      )}

      {pending && (
        <div className="mt-3 space-y-2">
          <PinMap
            position={pending.position}
            alternatives={pending.alternatives}
            onMove={(position) =>
              setPending((current) => (current ? { ...current, position } : current))
            }
          />
          <p className="text-xs text-gray-500">
            Arraste o pin ou toque no mapa para ajustar.
          </p>
          <div className="flex gap-2">
            <Button onClick={handleConfirmPin} disabled={busy} className="flex-1">
              {busy ? "Salvando..." : "Confirmar partida"}
            </Button>
            <Button variant="secondary" onClick={() => setPending(null)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {message && (
        <p
          role="status"
          className={`mt-2 text-sm ${message.error ? "text-red-600" : "text-green-700"}`}
        >
          {message.text}
        </p>
      )}
    </section>
  );
}
