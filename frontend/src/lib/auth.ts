const TOKEN_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;

  const payload = parseJwtPayload(token);
  if (!payload) {
    clearTokens();
    return false;
  }

  // Check token expiry
  const exp = payload.exp as number | undefined;
  if (exp && exp * 1000 < Date.now()) {
    clearTokens();
    return false;
  }

  // Verify token has required fields
  if (!payload.sub || !payload.role || payload.type !== "access") {
    clearTokens();
    return false;
  }

  return true;
}

export function getCurrentUserRole(): string | null {
  const token = getToken();
  if (!token) return null;
  const payload = parseJwtPayload(token);
  return (payload?.role as string) ?? null;
}
