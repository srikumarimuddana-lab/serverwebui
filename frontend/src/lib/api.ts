import { getToken, setTokens, clearTokens } from "./auth";
import type { Server } from "@/types";

const MASTER_URL = process.env.NEXT_PUBLIC_MASTER_URL || "http://localhost:8400";

export function getServers(): Server[] {
  if (typeof window === "undefined") return [];
  const raw = localStorage.getItem("servers_config");
  return raw ? JSON.parse(raw) : [];
}

export function getApiBase(server: Server): string {
  if (server.mode === "linux-fleet") {
    return `${MASTER_URL}/agents/${server.id}`;
  }
  return `https://${server.ip_address}:${server.port}`;
}

async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (!headers["Content-Type"] && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    clearTokens();
    window.location.href = "/login";
  }

  return response;
}

export async function login(username: string, password: string): Promise<boolean> {
  const resp = await fetch(`${MASTER_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) return false;
  const data = await resp.json();
  setTokens(data.access_token, data.refresh_token);
  return true;
}

export async function fetchStats(server: Server) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/stats`);
  return resp.json();
}

export async function fetchFiles(server: Server, path: string) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/files/${encodeURIComponent(path)}`);
  return resp.json();
}

export async function fetchServices(server: Server) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/services`);
  return resp.json();
}

export async function controlService(server: Server, name: string, action: string) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/services/${name}/${action}`, { method: "POST" });
  return resp.json();
}

export async function fetchLogs(server: Server, path: string, offset = 0, limit = 50) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/logs/${encodeURIComponent(path)}?offset=${offset}&limit=${limit}`);
  return resp.json();
}

export async function fetchAgents() {
  const resp = await apiFetch(`${MASTER_URL}/agents`);
  return resp.json();
}

export function getTerminalWsUrl(server: Server): string {
  const base = getApiBase(server).replace("http", "ws");
  return `${base}/terminal/open`;
}
