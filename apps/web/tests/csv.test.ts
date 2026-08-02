import { describe, expect, it } from "vitest";

import { parseDeliveriesCsv } from "@/lib/csv";

describe("parseDeliveriesCsv", () => {
  it("importa um CSV válido", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "street,number,neighborhood,cep,complement\n" +
        "Avenida Major Amarante,1000,Centro,76980-075,\n" +
        "Rua Osório Duque Estrada,250,Jardim América,,Fundos\n",
    );

    expect(errors).toEqual([]);
    expect(deliveries).toEqual([
      {
        street: "Avenida Major Amarante",
        number: "1000",
        neighborhood: "Centro",
        cep: "76980-075",
        complement: null,
      },
      {
        street: "Rua Osório Duque Estrada",
        number: "250",
        neighborhood: "Jardim América",
        cep: null,
        complement: "Fundos",
      },
    ]);
  });

  it("aceita CSV só com as colunas obrigatórias", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "street,number,neighborhood\nRua A,10,Centro\n",
    );

    expect(errors).toEqual([]);
    expect(deliveries[0]).toEqual({
      street: "Rua A",
      number: "10",
      neighborhood: "Centro",
      cep: null,
      complement: null,
    });
  });

  it("aceita BOM, CRLF e colunas fora de ordem", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "﻿neighborhood,street,number\r\nCentro,Rua C,30\r\n",
    );

    expect(errors).toEqual([]);
    expect(deliveries[0].street).toBe("Rua C");
    expect(deliveries[0].neighborhood).toBe("Centro");
  });

  it("respeita vírgulas dentro de aspas", () => {
    const { deliveries } = parseDeliveriesCsv(
      'street,number,neighborhood\n"Rua Residencial Florença, Um",8046,Centro\n',
    );

    expect(deliveries[0].street).toBe("Rua Residencial Florença, Um");
  });

  it("reclama de colunas obrigatórias ausentes", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "address,latitude,longitude\nRua A,-12.7,-60.1\n",
    );

    expect(deliveries).toEqual([]);
    expect(errors[0]).toContain("colunas obrigatórias");
  });

  it("reporta linhas incompletas sem descartar as válidas", () => {
    const { deliveries, errors } = parseDeliveriesCsv(
      "street,number,neighborhood\nRua A,,Centro\n,10,Centro\nRua C,30,Centro\n",
    );

    expect(deliveries).toHaveLength(1);
    expect(deliveries[0].street).toBe("Rua C");
    expect(errors).toHaveLength(2);
    expect(errors[0]).toContain("Linha 2");
    expect(errors[0]).toContain("número");
    expect(errors[1]).toContain("Linha 3");
    expect(errors[1]).toContain("rua");
  });

  it("trata arquivo vazio", () => {
    expect(parseDeliveriesCsv("   ").errors[0]).toBe("Arquivo CSV vazio");
  });
});
