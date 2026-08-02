"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { login, register } from "@/lib/api";

export default function Login({
  onLoginSuccess,
}: {
  onLoginSuccess: (token: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegistering, setIsRegistering] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAuth = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = isRegistering
        ? await register(email, password)
        : await login(email, password);
      onLoginSuccess(data.access_token);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Erro ao conectar ao servidor",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <form
        onSubmit={handleAuth}
        className="w-full max-w-md space-y-4 rounded-lg bg-white p-8 shadow"
      >
        <h1 className="text-center text-3xl font-bold">
          Delivery Route Optimizer
        </h1>
        <p className="text-center text-sm text-gray-600">
          {isRegistering
            ? "Crie sua conta para começar"
            : "Entre para ver suas rotas"}
        </p>

        <Input
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="seu@email.com"
          required
        />

        <Input
          label="Senha"
          type="password"
          autoComplete={isRegistering ? "new-password" : "current-password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
          minLength={6}
          required
        />

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        <Button type="submit" disabled={loading} className="w-full">
          {loading
            ? isRegistering
              ? "Registrando..."
              : "Entrando..."
            : isRegistering
              ? "Registrar"
              : "Entrar"}
        </Button>

        <button
          type="button"
          onClick={() => {
            setIsRegistering(!isRegistering);
            setError("");
          }}
          className="w-full text-sm text-blue-600 hover:text-blue-700"
        >
          {isRegistering
            ? "Já tem conta? Entrar"
            : "Não tem conta? Registrar"}
        </button>
      </form>
    </div>
  );
}
