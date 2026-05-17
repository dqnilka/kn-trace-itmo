import type { BankEntranceResult, UserState } from '../types'
import { applyEntrance, clearMastery, loadMastery, saveMastery } from './mastery'

const USER_KEY = 'akt:user'
const RESULTS_KEY = 'akt:lastResults'
const UID_KEY = 'akt:uid'

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
    // UID тоже сбрасываем: следующий signup на этом устройстве получит свежий
    // непредсказуемый id и не унаследует mastery-историю предыдущего юзера.
    localStorage.removeItem(UID_KEY)
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

/**
 * Безопасный (для MVP) user_id: непредсказуемое 30-битное число.
 *
 * Раньше user_id выводился из FNV-hash email — это значило, что любой, кто
 * знает email, может подделать `user_id` в `/event` и испортить чужую
 * mastery-историю (бэк не валидирует). Теперь — `crypto.getRandomValues`
 * один раз на signup, сохраняем в localStorage и переиспользуем.
 *
 * Bэк-схема ожидает `user_id: int`, поэтому возвращаем число (не UUID-строку),
 * чтобы не ломать существующий API-контракт.
 *
 * Долгосрочно — JWT/сессионная кука с привязкой к user_id на бэке.
 */
export function userIdFromEmail(_email: string): number {
  return ensureUserId()
}

function ensureUserId(): number {
  try {
    const raw = localStorage.getItem(UID_KEY)
    if (raw) {
      const n = Number(raw)
      if (Number.isFinite(n) && n > 0) return n
    }
  } catch {
    // localStorage недоступен — fallback на одноразовый id
  }
  const id = generateUserId()
  try {
    localStorage.setItem(UID_KEY, String(id))
  } catch {
    // ignore
  }
  return id
}

function generateUserId(): number {
  // 30 бит — достаточно для разделения миллионов студентов и
  // помещается в положительный signed int32, который без сюрпризов
  // улетает на бэк как `user_id: int`.
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    const buf = new Uint32Array(1)
    crypto.getRandomValues(buf)
    return (buf[0] & 0x3fffffff) + 1 // [1, 2^30)
  }
  // SSR / очень старый браузер — fallback на Math.random
  return Math.floor(Math.random() * (1 << 30)) + 1
}
