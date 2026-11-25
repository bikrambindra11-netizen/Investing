"use client";

import { useEffect, useState } from "react";
import { API_BASE, type MarketStatus, type Tick } from "./api";

/** Live ticks and status from the backend's Server-Sent Events stream. */
export function useMarketStream() {
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/api/market/stream`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource reconnects by itself
    es.addEventListener("ticks", (e) => {
      const changed = JSON.parse((e as MessageEvent).data) as Record<string, Tick>;
      setTicks((prev) => ({ ...prev, ...changed }));
    });
    es.addEventListener("status", (e) => setStatus(JSON.parse((e as MessageEvent).data)));
    return () => es.close();
  }, []);

  return { ticks, status, backendConnected: connected };
}
