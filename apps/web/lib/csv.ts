import type { AddressInput } from "./types";

export interface CsvParseResult {
  deliveries: AddressInput[];
  errors: string[];
}

const REQUIRED_COLUMNS = ["street", "number", "neighborhood"] as const;

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
 * Converte o conteúdo de um CSV (colunas street, number, neighborhood e,
 * opcionalmente, cep e complement) em endereços. Linhas inválidas viram
 * mensagens em `errors` em vez de derrubar a importação inteira.
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

  const indexes = {
    street: headers.indexOf("street"),
    number: headers.indexOf("number"),
    neighborhood: headers.indexOf("neighborhood"),
    cep: headers.indexOf("cep"),
    complement: headers.indexOf("complement"),
  };

  const deliveries: AddressInput[] = [];

  lines.slice(1).forEach((line, index) => {
    const lineNumber = index + 2;
    const values = splitCsvLine(line);
    const at = (position: number) =>
      position >= 0 ? (values[position] ?? "").trim() : "";

    const street = at(indexes.street);
    const number = at(indexes.number);
    const neighborhood = at(indexes.neighborhood);

    const missingFields = [
      street ? null : "rua",
      number ? null : "número",
      neighborhood ? null : "bairro",
    ].filter(Boolean);

    if (missingFields.length > 0) {
      errors.push(`Linha ${lineNumber}: falta ${missingFields.join(", ")}`);
      return;
    }

    deliveries.push({
      street,
      number,
      neighborhood,
      cep: at(indexes.cep) || null,
      complement: at(indexes.complement) || null,
    });
  });

  return { deliveries, errors };
}
