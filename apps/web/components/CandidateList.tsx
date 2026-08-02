"use client";

import type { GeocodeCandidate } from "@/lib/types";

function formatDistance(meters: number | null | undefined): string | null {
  if (meters === null || meters === undefined) return null;
  if (meters < 1) return "no ponto atual";
  if (meters < 1000) return `a ${Math.round(meters)} m do pin atual`;
  return `a ${(meters / 1000).toFixed(1).replace(".", ",")} km do pin atual`;
}

/**
 * Opções que o Google devolveu para o mesmo endereço. Ler o endereço
 * formatado é o que deixa ela reconhecer o certo ("esse é o bairro certo") —
 * melhor do que arrastar o pin às cegas.
 */
export default function CandidateList({
  candidates,
  selected,
  onSelect,
}: {
  candidates: GeocodeCandidate[];
  selected?: { latitude: number; longitude: number } | null;
  onSelect: (candidate: GeocodeCandidate) => void;
}) {
  if (candidates.length < 2) {
    return null;
  }

  return (
    <div className="space-y-1">
      <p className="text-sm font-medium">Qual desses é o endereço certo?</p>
      <ul className="space-y-1">
        {candidates.map((candidate, index) => {
          const isSelected =
            selected?.latitude === candidate.latitude &&
            selected?.longitude === candidate.longitude;
          const distance = formatDistance(candidate.distance_m);

          return (
            <li key={`${candidate.latitude}-${candidate.longitude}-${index}`}>
              <button
                onClick={() => onSelect(candidate)}
                className={`w-full rounded border p-2 text-left text-sm transition-colors ${
                  isSelected
                    ? "border-blue-600 bg-blue-50"
                    : "border-gray-200 hover:bg-gray-50"
                }`}
              >
                <span className="mr-2 inline-block h-5 w-5 rounded-full bg-amber-500 text-center text-xs font-bold leading-5 text-white">
                  {index + 1}
                </span>
                {candidate.formatted_address ??
                  `${candidate.latitude.toFixed(5)}, ${candidate.longitude.toFixed(5)}`}
                {distance && (
                  <span className="mt-0.5 block text-xs text-gray-500">
                    {distance}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-gray-500">
        Se nenhum estiver certo, arraste o pin no mapa.
      </p>
    </div>
  );
}
