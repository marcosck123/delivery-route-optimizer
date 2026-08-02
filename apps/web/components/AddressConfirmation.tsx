"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import CandidateList from "@/components/CandidateList";
import { Button } from "@/components/ui/Button";
import { confirmPin } from "@/lib/api";
import { CITY_CENTER } from "@/lib/geo";
import type { Coordinates, Delivery, GeocodeStatus } from "@/lib/types";

// Leaflet depende de window — sem ssr:false o build da Vercel quebra.
const PinMap = dynamic(() => import("@/components/PinMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-80 items-center justify-center rounded-md bg-gray-100 text-gray-500">
      Carregando mapa...
    </div>
  ),
});

const STATUS_STYLE: Record<
  string,
  { border: string; badge: string; title: string }
> = {
  resolved: {
    border: "border-green-500 bg-green-50",
    badge: "bg-green-600",
    title: "Encontrado ✓ — É esse mesmo?",
  },
  needs_confirmation: {
    border: "border-amber-500 bg-amber-50",
    badge: "bg-amber-500",
    title: "Confira no mapa",
  },
  failed: {
    border: "border-red-500 bg-red-50",
    badge: "bg-red-600",
    title: "Marque o ponto no mapa",
  },
  pending: {
    border: "border-gray-300 bg-gray-50",
    badge: "bg-gray-500",
    title: "Aguardando busca do endereço",
  },
};

function fallbackPosition(delivery: Delivery): Coordinates {
  if (delivery.latitude !== null && delivery.longitude !== null) {
    return { latitude: delivery.latitude, longitude: delivery.longitude };
  }
  // Sem coordenada nenhuma: começa no centro da cidade para ela arrastar.
  return CITY_CENTER;
}

/**
 * Revisão dos endereços, um por vez. Ao confirmar, já pula para o próximo
 * pendente — ela não precisa clicar duas vezes por entrega.
 */
export default function AddressConfirmation({
  routeId,
  deliveries,
  token,
  onAllConfirmed,
  onDeliveryConfirmed,
}: {
  routeId: number;
  deliveries: Delivery[];
  token: string;
  onAllConfirmed: () => void;
  onDeliveryConfirmed: (delivery: Delivery) => void;
}) {
  const pending = useMemo(
    () => deliveries.filter((delivery) => delivery.geocode_status !== "confirmed"),
    [deliveries],
  );

  const [index, setIndex] = useState(0);
  const [position, setPosition] = useState<Coordinates | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const current = pending[index];
  const confirmedCount = deliveries.length - pending.length;

  useEffect(() => {
    setPosition(current ? fallbackPosition(current) : null);
    setError("");
  }, [current]);

  useEffect(() => {
    if (pending.length > 0 && index >= pending.length) {
      setIndex(pending.length - 1);
    }
  }, [pending.length, index]);

  if (!current || !position) {
    return null;
  }

  const style = STATUS_STYLE[current.geocode_status] ?? STATUS_STYLE.pending;

  const handleConfirm = async () => {
    setSaving(true);
    setError("");
    try {
      const updated = await confirmPin(
        routeId,
        current.id,
        position.latitude,
        position.longitude,
        token,
      );
      onDeliveryConfirmed(updated);

      if (pending.length <= 1) {
        onAllConfirmed();
      } else if (index >= pending.length - 1) {
        setIndex(0); // volta para o primeiro que ainda falta
      }
      // demais casos: a lista encolhe e o próximo entra sozinho neste índice
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Não foi possível salvar o ponto",
      );
    } finally {
      setSaving(false);
    }
  };

  const progress = `${confirmedCount + 1} de ${deliveries.length}`;

  return (
    <section className={`rounded-lg border-2 p-4 ${style.border}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-bold">Confirmar endereços</h3>
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold text-white ${style.badge}`}
        >
          {progress}
        </span>
      </div>

      <div className="mb-3">
        <p className="font-medium">{current.address}</p>
        <p className="text-sm text-gray-700">{style.title}</p>
        {current.geocode_message && (
          <p role="alert" className="mt-1 text-sm font-medium text-amber-800">
            {current.geocode_message}
          </p>
        )}
      </div>

      {current.geocode_alternatives && (
        <div className="mb-3">
          <CandidateList
            candidates={current.geocode_alternatives}
            selected={position}
            onSelect={(candidate) =>
              setPosition({
                latitude: candidate.latitude,
                longitude: candidate.longitude,
              })
            }
          />
        </div>
      )}

      <PinMap
        position={position}
        alternatives={current.geocode_alternatives ?? []}
        onMove={setPosition}
      />

      <p className="mt-2 text-xs text-gray-500">
        Arraste o pin ou toque no mapa para ajustar.
      </p>

      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={handleConfirm} disabled={saving} className="flex-1">
          {saving
            ? "Salvando..."
            : current.geocode_status === "resolved"
              ? "Sim, próximo"
              : "Confirmar"}
        </Button>
        {pending.length > 1 && (
          <Button
            variant="secondary"
            disabled={saving}
            onClick={() => setIndex((value) => (value + 1) % pending.length)}
          >
            Pular
          </Button>
        )}
      </div>
    </section>
  );
}

export type { GeocodeStatus };
