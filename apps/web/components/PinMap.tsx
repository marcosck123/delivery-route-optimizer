"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

import type { Coordinates } from "@/lib/types";

function pinIcon(color: string, label = "") {
  return L.divIcon({
    className: "delivery-marker",
    html: `<span style="background:${color}">${label}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

/**
 * Mapa de um ponto só, com marcador arrastável. Toda vez que o pin é solto,
 * `onMove` recebe a nova coordenada — o componente pai decide quando gravar.
 */
export default function PinMap({
  position,
  alternatives = [],
  onMove,
}: {
  position: Coordinates;
  alternatives?: Coordinates[];
  onMove: (coordinates: Coordinates) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const altLayerRef = useRef<L.LayerGroup | null>(null);
  const onMoveRef = useRef(onMove);

  useEffect(() => {
    onMoveRef.current = onMove;
  }, [onMove]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current).setView(
      [position.latitude, position.longitude],
      17,
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);

    const marker = L.marker([position.latitude, position.longitude], {
      draggable: true,
      icon: pinIcon("#2563eb"),
    }).addTo(map);

    marker.on("dragend", () => {
      const { lat, lng } = marker.getLatLng();
      onMoveRef.current({ latitude: lat, longitude: lng });
    });

    // Clicar no mapa também move o pin — mais fácil que arrastar no celular.
    map.on("click", (event: L.LeafletMouseEvent) => {
      marker.setLatLng(event.latlng);
      onMoveRef.current({
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
      });
    });

    mapRef.current = map;
    markerRef.current = marker;
    altLayerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
      altLayerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reposiciona quando o pai troca de entrega
  useEffect(() => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (!map || !marker) return;

    marker.setLatLng([position.latitude, position.longitude]);
    map.setView([position.latitude, position.longitude], map.getZoom());
  }, [position.latitude, position.longitude]);

  // Candidatos divergentes: clicáveis, para escolher em vez de arrastar
  useEffect(() => {
    const layer = altLayerRef.current;
    if (!layer) return;

    layer.clearLayers();
    alternatives.forEach((candidate, index) => {
      L.marker([candidate.latitude, candidate.longitude], {
        icon: pinIcon("#f59e0b", String(index + 1)),
      })
        .bindTooltip(`Opção ${index + 1} — clique para usar`)
        .on("click", () => onMoveRef.current(candidate))
        .addTo(layer);
    });
  }, [alternatives]);

  return <div ref={containerRef} className="h-80 w-full rounded-md" />;
}
