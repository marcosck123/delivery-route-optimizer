import type { DeliveryInput } from "./types";

export interface CsvParseResult {
  deliveries: DeliveryInput[];
  errors: string[];
}

const REQUIRED_COLUMNS = ["address", "latitude", "longitude"] as const;

/** Divide uma linha de CSV respeitando aspas duplas. */
function splitCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let insideQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];

    if (char === '"') {
      if (insideQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        insideQuotes = !insideQuotes;
      }
    } else if (char === "," && !insideQuotes) {
      values.push(current);
      current = "";
    } else {
      current += char;
    }
  }

  values.push(current);
  return values.map((value) => value.trim());
}

/**
 * Converte o conteúdo de um CSV (colunas address, latitude, longitude) em
 * entregas. Linhas inválidas viram mensagens em `errors` em vez de derrubar
 * a importação inteira.
 */
export function parseDeliveriesCsv(content: string): CsvParseResult {
  const errors: string[] = [];
  const lines = content
    .replace(/^﻿/, "")
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0);

  if (lines.length === 0) {
    return { deliveries: [], errors: ["Arquivo CSV vazio"] };
  }

  const headers = splitCsvLine(lines[0]).map((header) => header.toLowerCase());
  const missing = REQUIRED_COLUMNS.filter((column) => !headers.includes(column));
  if (missing.length > 0) {
    return {
      deliveries: [],
      errors: [`CSV sem as colunas obrigatórias: ${missing.join(", ")}`],
    };
  }

  const addressIndex = headers.indexOf("address");
  const latitudeIndex = headers.indexOf("latitude");
  const longitudeIndex = headers.indexOf("longitude");

  const deliveries: DeliveryInput[] = [];

  lines.slice(1).forEach((line, index) => {
    const lineNumber = index + 2;
    const values = splitCsvLine(line);
    const address = values[addressIndex] ?? "";
    const latitude = Number(values[latitudeIndex]);
    const longitude = Number(values[longitudeIndex]);

    if (!address) {
      errors.push(`Linha ${lineNumber}: endereço vazio`);
      return;
    }
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      errors.push(`Linha ${lineNumber}: latitude/longitude inválidas`);
      return;
    }
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
      errors.push(`Linha ${lineNumber}: coordenadas fora do intervalo válido`);
      return;
    }

    deliveries.push({ address, latitude, longitude });
  });

  return { deliveries, errors };
}
