"use client";

/**
 * Live board subscription.
 *
 * Frames are treated as *hints*, not as data: on receipt the hook invalidates
 * the relevant React Query keys and the client refetches over REST. That costs
 * one extra request per event and buys an important property — a dropped,
 * duplicated, or out-of-order frame can never leave the board showing a state
 * the server does not agree with. On a screen people commit resources from,
 * that trade is worth making.
 */

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { WS_BASE, loadSession } from "./api";
import type { PresenceEntry, WsFrame } from "./types";

export type ConnectionState = "connecting" | "open" | "closed";

interface LiveBoard {
  state: ConnectionState;
  presence: PresenceEntry[];
  lastEvent: WsFrame | null;
  /** Bumped on every frame; useful as a "something changed" signal. */
  version: number;
}

const RECONNECT_MS = 3000;
const KEEPALIVE_MS = 25000;

export function useIncidentSocket(incidentId: string | undefined): LiveBoard {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ConnectionState>("connecting");
  const [presence, setPresence] = useState<PresenceEntry[]>([]);
  const [lastEvent, setLastEvent] = useState<WsFrame | null>(null);
  const [version, setVersion] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const keepaliveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const closedByUs = useRef(false);

  useEffect(() => {
    if (!incidentId) return;
    closedByUs.current = false;

    const connect = () => {
      const session = loadSession();
      const url = new URL(`${WS_BASE}/api/ws/incidents/${incidentId}`);
      if (session?.token) url.searchParams.set("token", session.token);

      let socket: WebSocket;
      try {
        socket = new WebSocket(url.toString());
      } catch {
        setState("closed");
        return;
      }
      socketRef.current = socket;
      setState("connecting");

      socket.onopen = () => {
        setState("open");
        keepaliveRef.current = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send("ping");
        }, KEEPALIVE_MS);
      };

      socket.onmessage = (message) => {
        let frame: WsFrame;
        try {
          frame = JSON.parse(message.data as string) as WsFrame;
        } catch {
          return;
        }
        if (frame.type === "pong") return;

        setLastEvent(frame);
        setVersion((n) => n + 1);

        if (frame.type === "connected" || frame.type === "presence.updated") {
          const next = frame.payload.presence as PresenceEntry[] | undefined;
          if (next) setPresence(next);
        }

        // Refetch rather than patching the cache from the frame. See the note
        // at the top of this file.
        switch (frame.type) {
          case "activity.created":
            void queryClient.invalidateQueries({ queryKey: ["board"] });
            break;
          case "request.created":
          case "request.updated":
          case "inventory.updated":
            void queryClient.invalidateQueries({ queryKey: ["board"] });
            void queryClient.invalidateQueries({ queryKey: ["requests"] });
            void queryClient.invalidateQueries({ queryKey: ["inventory"] });
            void queryClient.invalidateQueries({ queryKey: ["audit"] });
            break;
          case "agent.completed":
            void queryClient.invalidateQueries({ queryKey: ["board"] });
            void queryClient.invalidateQueries({ queryKey: ["agents"] });
            void queryClient.invalidateQueries({ queryKey: ["audit"] });
            break;
          default:
            break;
        }
      };

      socket.onclose = () => {
        setState("closed");
        if (keepaliveRef.current) clearInterval(keepaliveRef.current);
        // The board must survive an API restart without a page reload.
        if (!closedByUs.current) {
          reconnectRef.current = setTimeout(connect, RECONNECT_MS);
        }
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      closedByUs.current = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (keepaliveRef.current) clearInterval(keepaliveRef.current);
      socketRef.current?.close();
    };
  }, [incidentId, queryClient]);

  return { state, presence, lastEvent, version };
}
