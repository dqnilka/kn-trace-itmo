import type { AuthUser } from '../types'

const TOKEN_KEY = 'akt:token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // ignore
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // ignore
  }
}

/** Decode the JWT payload (no verification — UI hint only). */
export function decodeUser(token: string | null): AuthUser | null {
  if (!token) return null
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.exp && payload.exp * 1000 < Date.now()) return null
    return {
      id: Number(payload.sub),
      email: String(payload.email || ''),
      display_name: null,
      is_admin: !!payload.is_admin,
    }
  } catch {
    return null
  }
}
