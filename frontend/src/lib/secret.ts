/** Shared CRON_SECRET handling for crawl-trigger actions (Refresh + Run now). */

const KEY = "carcatcher_cron_secret";

export function getStoredSecret(): string | null {
  return localStorage.getItem(KEY);
}

export function clearSecret(): void {
  localStorage.removeItem(KEY);
}

/** Return the stored secret, or prompt for one once and store it. */
export function ensureSecret(): string | null {
  const existing = getStoredSecret();
  if (existing) return existing;
  const entered = window.prompt("Enter your refresh secret (CRON_SECRET):")?.trim();
  if (!entered) return null;
  localStorage.setItem(KEY, entered);
  return entered;
}
