import type { Coordinates } from "./types";

/**
 * Vilhena/RO — ponto de partida do pin quando o geocoding não devolveu nada.
 *
 * Mora aqui, e não em PinMap.tsx, de propósito: qualquer import estático de um
 * módulo que carrega Leaflet coloca `window` no bundle do servidor e quebra o
 * prerender da Vercel, mesmo quando o componente é carregado via
 * `next/dynamic` com `ssr:false`.
 */
export const CITY_CENTER: Coordinates = {
  latitude: -12.7406,
  longitude: -60.1458,
};
