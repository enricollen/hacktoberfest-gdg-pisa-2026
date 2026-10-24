/** Shop slug from /s/<shop>/... (the QR code path); the demo shop otherwise. */
export function shopSlug(): string {
  return window.location.pathname.match(/^\/s\/([\w-]+)/)?.[1] ?? 'demo'
}
