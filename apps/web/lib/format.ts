/** Small presentation helpers shared across views. */

import { clsx } from "clsx";
import type { ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Time of day in 24h, which is how a duty floor reads a log. */
export function clockTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function dateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** "2h 14m ago" — relative age, which is what matters during an incident. */
export function since(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours < 24) return remainder ? `${hours}h ${remainder}m ago` : `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Countdown to the end of the operational period, or "OVERDUE". */
export function untilPeriodEnd(endIso: string): string {
  const end = new Date(endIso).getTime();
  if (Number.isNaN(end)) return "";
  const seconds = Math.floor((end - Date.now()) / 1000);
  if (seconds <= 0) return "OVERDUE";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")} left`;
}

export function titleCase(value: string): string {
  return value
    .replace(/[_.]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .trim();
}

/** Two-letter avatar token, e.g. "LOGISTICS-2" -> "L2", "IC-Demo" -> "ID". */
export function initials(name: string): string {
  const cleaned = name.replace(/[^A-Za-z0-9]+/g, " ").trim();
  const parts = cleaned.split(" ").filter(Boolean);
  if (parts.length === 0) return "??";
  if (parts.length === 1) return (parts[0] ?? "").slice(0, 2).toUpperCase();
  return `${(parts[0] ?? "")[0] ?? ""}${(parts[parts.length - 1] ?? "")[0] ?? ""}`.toUpperCase();
}

export function shortHash(hash: string, length = 10): string {
  return hash ? `${hash.slice(0, length)}…` : "";
}

export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}
