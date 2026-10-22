import { useEffect, useState } from "react";
import { getHealth } from "./api";
import type { Health } from "./types";

// Polls until the speech model is ready (the backend loads it at startup,
// ~12 s, D52), then stops.
export function useHealth(intervalMs = 1500): Health | null {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      let next: Health | null = null;
      try {
        next = await getHealth();
      } catch {
        next = null; // server not reachable yet
      }
      if (cancelled) return;
      setHealth(next);
      if (!next || next.status === "warming_up") timer = window.setTimeout(poll, intervalMs);
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [intervalMs]);
  return health;
}
