import type { BankEntranceResult, UserState } from '../types'
import { applyEntrance, clearMastery, loadMastery, saveMastery } from './mastery'

const USER_KEY = 'akt:user'
const RESULTS_KEY = 'akt:lastResults'

function safeRead<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function safeWrite(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // localStorage may be disabled — fail silently
  }
}

export function loadUser(): UserState | null {
  return safeRead<UserState>(USER_KEY)
}

export function saveUser(user: UserState): void {
  safeWrite(USER_KEY, user)
}

export function clearUser(): void {
  try {
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(RESULTS_KEY)
  } catch {
    // ignore
  }
  clearMastery()
}

export function loadLastResults(): BankEntranceResult | null {
  const v = safeRead<BankEntranceResult>(RESULTS_KEY)
  // Schema guard: older versions stored `per_topic` instead of `per_chapter`.
  if (!v || typeof v !== 'object' || !v.per_chapter || !Array.isArray(v.answers)) {
    try {
      localStorage.removeItem(RESULTS_KEY)
    } catch {
      // ignore
    }
    return null
  }
  return v
}

export function saveLastResults(r: BankEntranceResult): void {
  safeWrite(RESULTS_KEY, r)
  // Replay entrance answers into the mastery store so the trainer knows weak spots.
  // We intentionally additive-apply: a re-take strengthens signal rather than wipes it.
  saveMastery(applyEntrance(loadMastery(), r))
}

export function userIdFromEmail(email: string): number {
  let h = 2166136261
  for (let i = 0; i < email.length; i++) {
    h ^= email.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return Math.abs(h) % 1_000_000
}
