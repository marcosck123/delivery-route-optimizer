"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { addDelivery, uploadOcrImage } from "@/lib/api";
import type { OcrBlock } from "@/lib/types";

interface EditableBlock {
  raw_text: string;
  street: string;
  number: string;
  neighborhood: string;
  complement: string;
  cep: string;
}

function toEditable(block: OcrBlock): EditableBlock {
  return {
    raw_text: block.raw_text,
    street: block.street ?? "",
    number: block.number ?? "",
    neighborhood: block.neighborhood ?? "",
    complement: "",
    cep: "",
  };
}

/**
 * Importa endereços de um print da lista de entregas. O OCR erra 1-2 letras
 * aqui e ali, por isso todo campo é editável e o texto lido fica à vista.
 */
export default function PhotoImport({
  routeId,
  token,
  onAdded,
}: {
  routeId: number;
  token: string;
  onAdded: () => void;
}) {
  const [blocks, setBlocks] = useState<EditableBlock[] | null>(null);
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setReading(true);
    setMessage(null);
    try {
      const result = await uploadOcrImage(routeId, file, token);
      setBlocks(result.blocks.map(toEditable));
      setMessage({ text: result.message, error: result.blocks.length === 0 });
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Não consegui ler a imagem",
        error: true,
      });
    } finally {
      setReading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const updateBlock = (
    index: number,
    field: keyof Omit<EditableBlock, "raw_text">,
    value: string,
  ) => {
    setBlocks((current) =>
      current
        ? current.map((block, i) =>
            i === index ? { ...block, [field]: value } : block,
          )
        : current,
    );
  };

  const removeBlock = (index: number) => {
    setBlocks((current) =>
      current ? current.filter((_, i) => i !== index) : current,
    );
  };

  const handleAddAll = async () => {
    if (!blocks || blocks.length === 0) return;

    const incomplete = blocks.filter(
      (block) => !block.street.trim() || !block.number.trim() || !block.neighborhood.trim(),
    );
    if (incomplete.length > 0) {
      setMessage({
        text: `Complete rua, número e bairro de ${incomplete.length} endereço(s)`,
        error: true,
      });
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      for (const block of blocks) {
        await addDelivery(
          routeId,
          {
            street: block.street.trim(),
            number: block.number.trim(),
            neighborhood: block.neighborhood.trim(),
            cep: block.cep.trim() || null,
            complement: block.complement.trim() || null,
          },
          token,
        );
      }
      setMessage({
        text: `${blocks.length} endereço(s) adicionado(s) à rota`,
        error: false,
      });
      setBlocks(null);
      onAdded();
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Erro ao adicionar endereços",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-1 text-xl font-bold">Importar por foto</h2>
      <p className="mb-4 text-xs text-gray-500">
        Para melhor leitura, dê zoom no app antes do print ou capture menos
        entregas por tela.
      </p>

      <label className="block cursor-pointer rounded-md bg-gray-200 px-4 py-2 text-center font-medium text-gray-900 hover:bg-gray-300">
        {reading ? "Lendo a imagem..." : "Escolher print"}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFile}
          disabled={reading}
          className="hidden"
        />
      </label>

      {message && (
        <p
          role="status"
          className={`mt-3 text-sm ${message.error ? "text-red-600" : "text-green-700"}`}
        >
          {message.text}
        </p>
      )}

      {blocks && blocks.length > 0 && (
        <div className="mt-4 space-y-4">
          <p className="text-sm font-medium">
            Confira o que foi lido ({blocks.length}):
          </p>

          {blocks.map((block, index) => (
            <div
              key={index}
              className="space-y-2 rounded border border-gray-200 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <pre className="max-h-24 flex-1 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-600">
                  {block.raw_text}
                </pre>
                <button
                  onClick={() => removeBlock(index)}
                  aria-label={`Descartar endereço ${index + 1}`}
                  className="shrink-0 text-sm text-red-600 hover:text-red-800"
                >
                  Descartar
                </button>
              </div>

              <Input
                label={`Rua ${index + 1}`}
                value={block.street}
                onChange={(event) =>
                  updateBlock(index, "street", event.target.value)
                }
              />
              <div className="grid grid-cols-2 gap-2">
                <Input
                  label={`Número ${index + 1}`}
                  value={block.number}
                  onChange={(event) =>
                    updateBlock(index, "number", event.target.value)
                  }
                />
                <Input
                  label={`Complemento ${index + 1}`}
                  value={block.complement}
                  onChange={(event) =>
                    updateBlock(index, "complement", event.target.value)
                  }
                />
              </div>
              <Input
                label={`Bairro ${index + 1}`}
                value={block.neighborhood}
                onChange={(event) =>
                  updateBlock(index, "neighborhood", event.target.value)
                }
              />
              <Input
                label={`CEP ${index + 1}`}
                value={block.cep}
                onChange={(event) => updateBlock(index, "cep", event.target.value)}
              />
            </div>
          ))}

          <Button onClick={handleAddAll} disabled={saving} className="w-full">
            {saving ? "Adicionando..." : "Adicionar à rota"}
          </Button>
        </div>
      )}
    </section>
  );
}
