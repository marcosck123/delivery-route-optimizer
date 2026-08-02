"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

import { sortDeliveries } from "@/lib/route";
import type { Route } from "@/lib/types";

const DEFAULT_CENTER: [number, number] = [-12.7406, -60.1458]; // Vilhena/RO
const DEFAULT_ZOOM = 13;

function markerIcon(index: number) {
  return L.divIcon({
    className: `delivery-marker${index === 0 ? " is-start" : ""}`,
    html: `<span>${index + 1}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
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

    const deliveries = sortDeliveries(route?.deliveries ?? []);
    if (deliveries.length === 0) {
      map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
      return;
    }

    deliveries.forEach((delivery, index) => {
      L.marker([delivery.latitude, delivery.longitude], {
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
        : deliveries.map((delivery) => [delivery.latitude, delivery.longitude]);

    if (points.length > 1) {
      L.polyline(points, {
        color: "#2563eb",
        weight: 4,
        opacity: 0.8,
        dashArray: osrmGeometry ? undefined : "6 8",
      }).addTo(layer);
    }

    const bounds = L.latLngBounds(
      deliveries.map((delivery) => [delivery.latitude, delivery.longitude]),
    );
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
  }, [route]);

  return <div ref={containerRef} className="h-[500px] w-full" />;
}
