/**
 * Top-level (full document) navigation, for flows that must leave the SPA —
 * e.g. OAuth sign-in, where the backend redirects on to the provider.
 * Isolated in a module so tests can mock it: jsdom's `window.location` is
 * unforgeable and cannot be stubbed directly.
 */
export function hardNavigate(url: string): void {
  window.location.assign(url);
}
