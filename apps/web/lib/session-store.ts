"use client";

/**
 * The session as an external store.
 *
 * `localStorage` is genuinely an external store, so it is read through
 * `useSyncExternalStore` rather than copied into React state inside an effect.
 * That avoids the cascading render React now warns about, removes any
 * hydration mismatch (the server snapshot is simply "signed out"), and gives
 * cross-tab synchronisation for free.
 *
 * The one rule that matters here: `getSnapshot` must return a **stable
 * reference** between changes, or React re-renders forever. Hence the cache.
 */

import { loadSession, saveSession } from "./api";
import type { Session } from "./types";

const listeners = new Set<() => void>();

// `undefined` means "not read from storage yet"; null means "signed out".
let cache: Session | null | undefined;

function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab signing in or out should update this one.
  const onStorage = () => {
    cache = loadSession();
    emit();
  };
  if (typeof window !== "undefined") window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") window.removeEventListener("storage", onStorage);
  };
}

export function getSnapshot(): Session | null {
  if (cache === undefined) cache = loadSession();
  return cache;
}

/** Rendered on the server and during hydration: nobody is signed in yet. */
export function getServerSnapshot(): Session | null {
  return null;
}

export function setStoredSession(session: Session | null): void {
  saveSession(session);
  cache = session;
  emit();
}

/**
 * True once the client has taken over from the server-rendered tree.
 *
 * Used to tell "signed out" apart from "not yet known", so the role switcher
 * can show a placeholder instead of briefly claiming the user is signed out.
 */
export function subscribeHydrated(): () => void {
  return () => {};
}

export function getHydratedSnapshot(): boolean {
  return true;
}

export function getHydratedServerSnapshot(): boolean {
  return false;
}
