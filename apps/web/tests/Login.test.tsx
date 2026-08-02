import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import Login from "@/components/Login";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(response: Partial<Response> & { json: () => Promise<unknown> }) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, ...response });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Login", () => {
  it("envia email e senha e devolve o token", async () => {
    const fetchMock = mockFetch({
      json: async () => ({ access_token: "token-123" }),
    });
    const onLoginSuccess = vi.fn();

    render(<Login onLoginSuccess={onLoginSuccess} />);

    await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
    await userEvent.type(screen.getByLabelText("Senha"), "senha123");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(onLoginSuccess).toHaveBeenCalledWith("token-123"));

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/login");
    expect(JSON.parse(options.body)).toEqual({
      email: "user@example.com",
      password: "senha123",
    });
  });

  it("mostra o erro devolvido pela API", async () => {
    mockFetch({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Email ou senha inválidos" }),
    });

    render(<Login onLoginSuccess={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Email"), "user@example.com");
    await userEvent.type(screen.getByLabelText("Senha"), "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email ou senha inválidos",
    );
  });

  it("alterna para o modo de registro", async () => {
    const fetchMock = mockFetch({ json: async () => ({ access_token: "novo" }) });

    render(<Login onLoginSuccess={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Não tem conta? Registrar" }),
    );

    await userEvent.type(screen.getByLabelText("Email"), "novo@example.com");
    await userEvent.type(screen.getByLabelText("Senha"), "senha123");
    await userEvent.click(screen.getByRole("button", { name: "Registrar" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls[0][0]).toContain("/api/auth/register"),
    );
  });
});
