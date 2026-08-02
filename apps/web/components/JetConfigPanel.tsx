"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError, getJetConfig, saveJetConfig } from "@/lib/api";

export default function JetConfigPanel({ token }: { token: string }) {
  const [jetUsername, setJetUsername] = useState("");
  const [jetApiKey, setJetApiKey] = useState("");
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(
    null,
  );

  useEffect(() => {
    getJetConfig(token)
      .then((config) => {
        setJetUsername(config.jet_username);
        setConfigured(true);
      })
      .catch((err) => {
        // 404 = ainda não configurado, é o estado normal na primeira visita
        if (!(err instanceof ApiError && err.status === 404)) {
          setMessage({ text: "Erro ao carregar credenciais J&T", error: true });
        }
      });
  }, [token]);

  const handleSave = async () => {
    if (!jetUsername.trim() || !jetApiKey.trim()) {
      setMessage({ text: "Preencha usuário e chave de API", error: true });
      return;
    }

    setLoading(true);
    try {
      await saveJetConfig(jetUsername.trim(), jetApiKey.trim(), token);
      setConfigured(true);
      setJetApiKey("");
      setMessage({ text: "Credenciais salvas", error: false });
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : "Erro ao salvar",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-lg bg-white p-6 shadow">
      <h2 className="mb-1 text-xl font-bold">Integração J&amp;T Express</h2>
      <p className="mb-4 text-xs text-gray-500">
        {configured
          ? "Credenciais configuradas. Use “Sincronizar J&T” na rota."
          : "Configure suas credenciais para importar pedidos automaticamente."}
      </p>

      <div className="space-y-3">
        <Input
          label="Usuário J&T"
          value={jetUsername}
          onChange={(event) => setJetUsername(event.target.value)}
          placeholder="conta-api"
        />
        <Input
          label="Chave de API"
          type="password"
          value={jetApiKey}
          onChange={(event) => setJetApiKey(event.target.value)}
          placeholder="••••••••"
        />

        {message && (
          <p
            className={`text-sm ${message.error ? "text-red-600" : "text-green-700"}`}
          >
            {message.text}
          </p>
        )}

        <Button
          onClick={handleSave}
          disabled={loading}
          variant="secondary"
          className="w-full"
        >
          {loading ? "Salvando..." : "Salvar credenciais"}
        </Button>
      </div>
    </section>
  );
}
