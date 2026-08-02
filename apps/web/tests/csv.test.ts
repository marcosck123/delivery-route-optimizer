import { describe, expect, it } from "vitest";

import { parseDeliveriesCsv } from "@/lib/csv";

describe("parseDeliveriesCsv", () => {
  it("importa um CSV válido", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "address,latitude,longitude\nRua A 10,-12.7406,-60.1458\nRua B 20,-12.7452,-60.1391\n",
    );

    expect(errors).toEqual([]);
    expect(deliveries).toEqual([
      { address: "Rua A 10", latitude: -12.7406, longitude: -60.1458 },
      { address: "Rua B 20", latitude: -12.7452, longitude: -60.1391 },
    ]);
  });

  it("aceita BOM, CRLF e colunas fora de ordem", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "﻿latitude,longitude,address\r\n-12.74,-60.14,Rua C\r\n",
    );

    expect(errors).toEqual([]);
    expect(deliveries).toEqual([
      { address: "Rua C", latitude: -12.74, longitude: -60.14 },
    ]);
  });

  it("respeita vírgulas dentro de aspas", () => {
    const { deliveries } = parseDeliveriesCsv(
      'address,latitude,longitude\n"Rua A, 123, Vilhena",-12.74,-60.14\n',
    );

    expect(deliveries[0].address).toBe("Rua A, 123, Vilhena");
  });

  it("reclama de colunas obrigatórias ausentes", () => {
    const { deliveries, errors } = parseDeliveriesCsv("endereco,lat\nRua A,1\n");

    expect(deliveries).toEqual([]);
    expect(errors[0]).toContain("colunas obrigatórias");
  });

  it("reporta linhas inválidas sem descartar as válidas", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "address,latitude,longitude\nRua A,abc,-60.14\n,-12.74,-60.14\nRua C,-12.74,-60.14\n",
    );

    expect(deliveries).toHaveLength(1);
    expect(deliveries[0].address).toBe("Rua C");
    expect(errors).toHaveLength(2);
    expect(errors[0]).toContain("Linha 2");
    expect(errors[1]).toContain("Linha 3");
  });

  it("rejeita coordenadas fora do intervalo", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "address,latitude,longitude\nRua A,200,-60.14\n",
    );

    expect(deliveries).toEqual([]);
    expect(errors[0]).toContain("fora do intervalo");
  });

  it("trata arquivo vazio", () => {
    expect(parseDeliveriesCsv("   ").errors[0]).toBe("Arquivo CSV vazio");
  });
});
