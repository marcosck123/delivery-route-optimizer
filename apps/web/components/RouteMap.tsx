"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

import { sortDeliveries } from "@/lib/route";
import { isReady, type Coordinates, type Route } from "@/lib/types";

const DEFAULT_CENTER: [number, number] = [-12.7406, -60.1458]; // Vilhena/RO
const DEFAULT_ZOOM = 13;

function markerIcon(index: number) {
  return L.divIcon({
    className: "delivery-marker",
    html: `<span>${index + 1}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

// O ponto de partida não é uma parada: verde e escrito, para não se confundir
// com a numeração das entregas.
function startIcon() {
  return L.divIcon({
    className: "delivery-marker is-start",
    html: `<span>&#9873;</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

export default function RouteMap({ route }: { route: Route | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  // Cria o mapa uma única vez
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);

    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  // Redesenha marcadores e traçado sempre que a rota muda
  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;

    layer.clearLayers();

    const start =
      route?.start_latitude !== null &&
      route?.start_latitude !== undefined &&
      route?.start_longitude !== null &&
      route?.start_longitude !== undefined
        ? { latitude: route.start_latitude, longitude: route.start_longitude }
        : null;

    if (start) {
      L.marker([start.latitude, start.longitude], { icon: startIcon() })
        .bindPopup(`<strong>Início</strong><br/>${route?.start_address ?? ""}`)
        .addTo(layer);
    }

    // Só entra no mapa quem já tem coordenada confiável.
    const deliveries = sortDeliveries(route?.deliveries ?? []).filter(isReady);
    if (deliveries.length === 0) {
      if (start) {
        map.setView([start.latitude, start.longitude], 15);
        return;
      }
      map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
      return;
    }

    const located = deliveries.map((delivery) => ({
      ...delivery,
      point: {
        latitude: delivery.latitude as number,
        longitude: delivery.longitude as number,
      } satisfies Coordinates,
    }));

    located.forEach((delivery, index) => {
      L.marker([delivery.point.latitude, delivery.point.longitude], {
        icon: markerIcon(index),
      })
        .bindPopup(`<strong>#${index + 1}</strong><br/>${delivery.address}`)
        .addTo(layer);
    });

    // Traçado real do OSRM (GeoJSON vem em [lon, lat]); sem ele, linha reta
    const osrmGeometry = route?.optimization_result?.osrm?.routes?.[0]?.geometry;
    const points: [number, number][] =
      osrmGeometry?.coordinates && osrmGeometry.coordinates.length > 0
        ? osrmGeometry.coordinates.map(([lon, lat]) => [lat, lon])
        : [
            ...(start ? [[start.latitude, start.longitude] as [number, number]] : []),
            ...located.map(
              (delivery) =>
                [delivery.point.latitude, delivery.point.longitude] as [
                  number,
                  number,
                ],
            ),
          ];

    if (points.length > 1) {
      L.polyline(points, {
        color: "#2563eb",
        weight: 4,
        opacity: 0.8,
        dashArray: osrmGeometry ? undefined : "6 8",
      }).addTo(layer);
    }

    const bounds = L.latLngBounds([
      ...(start ? [[start.latitude, start.longitude] as [number, number]] : []),
      ...located.map(
        (delivery) =>
          [delivery.point.latitude, delivery.point.longitude] as [number, number],
      ),
    ]);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
  }, [route]);

  return <div ref={containerRef} className="h-[500px] w-full" />;
}
