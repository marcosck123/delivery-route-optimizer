import type {
  AddressInput,
  Delivery,
  JetConfig,
  OcrUploadResponse,
  Route,
  RouteSummary,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export const TOKEN_STORAGE_KEY = "access_token";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, headers, ...rest } = options;

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(rest.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    // erros de validação do FastAPI vêm como lista de objetos
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((item) => item.msg ?? String(item)).join("; ");
    }
  } catch {
    // corpo não era JSON
  }
  return `Erro ${response.status} ao chamar a API`;
}

// --------------------------------------------------------------- auth

export const login = (email: string, password: string) =>
  request<{ access_token: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const register = (email: string, password: string) =>
  request<{ access_token: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const me = (token: string) =>
  request<{ id: number; email: string }>("/api/auth/me", { token });

// -------------------------------------------------------------- rotas

export const listRoutes = (token: string) =>
  request<RouteSummary[]>("/api/routes/", { token });

export const getRoute = (routeId: number, token: string) =>
  request<Route>(`/api/routes/${routeId}`, { token });

export const createRoute = (
  name: string,
  deliveries: AddressInput[],
  token: string,
) =>
  request<Route>("/api/routes/", {
    method: "POST",
    token,
    body: JSON.stringify({ name, deliveries }),
  });

export const deleteRoute = (routeId: number, token: string) =>
  request<void>(`/api/routes/${routeId}`, { method: "DELETE", token });

export const optimizeRoute = (routeId: number, token: string) =>
  request<Route>(`/api/routes/${routeId}/optimize`, { method: "POST", token });

export const syncJetOrders = (routeId: number, token: string) =>
  request<Route>(`/api/routes/${routeId}/sync-jet`, { method: "POST", token });

export const uploadCsv = (routeId: number, file: File, token: string) => {
  const formData = new FormData();
  formData.append("file", file);
  return request<{ message: string; added: number }>(
    `/api/routes/${routeId}/upload-csv`,
    { method: "POST", token, body: formData },
  );
};

// ---------------------------------------------------------- entregas

/** Lê os endereços de um print. Não cria nada — devolve para revisão. */
export const uploadOcrImage = (routeId: number, file: File, token: string) => {
  const formData = new FormData();
  formData.append("file", file);
  return request<OcrUploadResponse>(`/api/routes/${routeId}/ocr-upload`, {
    method: "POST",
    token,
    body: formData,
  });
};

/** Dispara o geocoding das entregas pendentes e devolve a lista atualizada. */
export const geocodeRoute = (routeId: number, token: string) =>
  request<Delivery[]>(`/api/routes/${routeId}/geocode`, {
    method: "POST",
    token,
  });

/** Grava o ponto que a usuária confirmou/arrastou no mapa. */
export const confirmPin = (
  routeId: number,
  deliveryId: number,
  latitude: number,
  longitude: number,
  token: string,
) =>
  request<Delivery>(
    `/api/routes/${routeId}/deliveries/${deliveryId}/confirm-pin`,
    {
      method: "POST",
      token,
      body: JSON.stringify({ delivery_id: deliveryId, latitude, longitude }),
    },
  );

export const addDelivery = (
  routeId: number,
  delivery: AddressInput & { jet_order_id?: string | null },
  token: string,
) =>
  request<Delivery>(`/api/routes/${routeId}/deliveries/`, {
    method: "POST",
    token,
    body: JSON.stringify(delivery),
  });

export const deleteDelivery = (
  routeId: number,
  deliveryId: number,
  token: string,
) =>
  request<void>(`/api/routes/${routeId}/deliveries/${deliveryId}`, {
    method: "DELETE",
    token,
  });

// -------------------------------------------------------------- J&T

export const getJetConfig = (token: string) =>
  request<JetConfig>("/api/jet-config/", { token });

export const saveJetConfig = (
  jetUsername: string,
  jetApiKey: string,
  token: string,
) =>
  request<JetConfig>("/api/jet-config/", {
    method: "PUT",
    token,
    body: JSON.stringify({ jet_username: jetUsername, jet_api_key: jetApiKey }),
  });
