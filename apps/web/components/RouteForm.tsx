"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { createRoute } from "@/lib/api";
import { parseDeliveriesCsv } from "@/lib/csv";
import type { AddressInput } from "@/lib/types";

const EMPTY_ADDRESS = {
  street: "",
  number: "",
  neighborhood: "",
  complement: "",
  cep: "",
};

export default function RouteForm({
  token,
  onRouteCreated,
}: {
  token: string;
  onRouteCreated: (routeId: number) => void;
}) {
  const [routeName, setRouteName] = useState("");
  const [deliveries, setDeliveries] = useState<AddressInput[]>([]);
  const [form, setForm] = useState(EMPTY_ADDRESS);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  const setField = (field: keyof typeof EMPTY_ADDRESS) => (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => setForm((current) => ({ ...current, [field]: event.target.value }));

  const handleAddDelivery = () => {
    const missing = [
      form.street.trim() ? null : "rua",
      form.number.trim() ? null : "número",
      form.neighborhood.trim() ? null : "bairro",
    ].filter(Boolean);

    if (missing.length > 0) {
      setMessage({ text: `Preencha: ${missing.join(", ")}`, error: true });
      return;
    }

    setDeliveries([
      ...deliveries,
      {
        street: form.street.trim(),
        number: form.number.trim(),
        neighborhood: form.neighborhood.trim(),
        cep: form.cep.trim() || null,
        complement: form.complement.trim() || null,
      },
    ]);
    setForm(EMPTY_ADDRESS);
    setMessage(null);
  };

  const handleRemoveDelivery = (index: number) => {
    setDeliveries(deliveries.filter((_, i) => i !== index));
  };

  const handleCsvUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const { deliveries: parsed, errors } = parseDeliveriesCsv(await file.text());
    setDeliveries((current) => [...current, ...parsed]);
    setMessage(
      errors.length > 0
        ? {
            text: `${parsed.length} importada(s). Problemas: ${errors.join("; ")}`,
            error: true,
          }
        : { text: `${parsed.length} endereço(s) importado(s) do CSV`, error: false },
    );

    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCreateRoute = async () => {
    if (!routeName.trim()) {
      setMessage({ text: "Dê um nome para a rota", error: true });
      return;
    }
    if (deliveries.length === 0) {
      setMessage({ text: "Adicione pelo menos um endereço", error: true });
      return;
    }

    setLoading(true);
    try {
      const route = await createRoute(routeName.trim(), deliveries, token);
      onRouteCreated(route.id);
      setRouteName("");
      setDeliveries([]);
      setMessage({ text: `Rota "${route.name}" criada`, error: false });
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Erro ao criar rota",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-6 text-2xl font-bold">Nova Rota</h2>

      <div className="space-y-4">
        <Input
          label="Nome da Rota"
          value={routeName}
          onChange={(event) => setRouteName(event.target.value)}
          placeholder="Ex: Segunda de Manhã"
        />

        <div>
          <label
            htmlFor="csv-upload"
            className="mb-2 block text-sm font-medium text-gray-700"
          >
            Importar CSV
          </label>
          <input
            id="csv-upload"
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={handleCsvUpload}
            className="w-full text-sm"
          />
          <p className="mt-1 text-xs text-gray-500">
            Colunas: street, number, neighborhood, cep, complement
          </p>
        </div>

        <div className="space-y-2 border-t pt-4">
          <h3 className="font-semibold">Adicionar endereço</h3>

          <Input
            label="Rua"
            value={form.street}
            onChange={setField("street")}
            placeholder="Av. Major Amarante"
          />

          <div className="grid grid-cols-2 gap-2">
            <Input
              label="Número"
              value={form.number}
              onChange={setField("number")}
              placeholder="1000"
            />
            <Input
              label="Complemento"
              value={form.complement}
              onChange={setField("complement")}
              placeholder="Casa / Ap 12"
            />
          </div>

          <Input
            label="Bairro"
            value={form.neighborhood}
            onChange={setField("neighborhood")}
            placeholder="Centro"
          />

          <Input
            label="CEP"
            value={form.cep}
            onChange={setField("cep")}
            placeholder="76980-000 (opcional)"
          />

          <Button onClick={handleAddDelivery} variant="secondary" className="w-full">
            + Adicionar
          </Button>
        </div>

        {deliveries.length > 0 && (
          <div className="border-t pt-4">
            <h3 className="mb-2 font-semibold">
              Endereços ({deliveries.length})
            </h3>
            <ul className="max-h-48 space-y-2 overflow-y-auto">
              {deliveries.map((delivery, index) => (
                <li
                  key={`${delivery.street}-${delivery.number}-${index}`}
                  className="flex items-center justify-between gap-2 rounded bg-gray-100 p-2"
                >
                  <span className="truncate text-sm">
                    {delivery.street}, {delivery.number} — {delivery.neighborhood}
                  </span>
                  <button
                    onClick={() => handleRemoveDelivery(index)}
                    className="shrink-0 text-sm text-red-600 hover:text-red-800"
                  >
                    Remover
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {message && (
          <p
            role="status"
            className={`text-sm ${message.error ? "text-red-600" : "text-green-700"}`}
          >
            {message.text}
          </p>
        )}

        <Button onClick={handleCreateRoute} disabled={loading} className="w-full">
          {loading ? "Criando..." : "Criar Rota"}
        </Button>
      </div>
    </section>
  );
}
