"use client";

import { useEffect, useMemo, useState } from "react";
import { IndexTiles } from "@/components/IndexTiles";
import { LiveBanner } from "@/components/LiveBanner";
import { Movers } from "@/components/Movers";
import { StockTable } from "@/components/StockTable";
import { getJSON, mergeLive, type IndexTile, type StocksResponse } from "@/lib/api";
import { useMarketStream } from "@/lib/useMarketStream";

export default function MarketPage() {
  const [stocks, setStocks] = useState<StocksResponse | null>(null);
  const [tiles, setTiles] = useState<IndexTile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { ticks, status, backendConnected } = useMarketStream();

  // Load once, and again whenever a background data refresh finishes.
  const refreshedAt = Object.values(status?.jobs ?? {}).map((j) => j.at).sort().at(-1);
  useEffect(() => {
    Promise.all([getJSON<StocksResponse>("/api/market/stocks"), getJSON<IndexTile[]>("/api/market/indices")])
      .then(([s, t]) => { setStocks(s); setTiles(t); setError(null); })
      .catch((e) => setError(`Could not load market data (${e.message}). Is the backend running?`));
  }, [refreshedAt]);

  const rows = useMemo(() => (stocks?.rows ?? []).map((r) => mergeLive(r, ticks[r.key])), [stocks, ticks]);
  const loading = stocks != null && stocks.count === 0;

  return (
    <div className="space-y-4">
      <LiveBanner status={status} backendConnected={backendConnected} asOf={stocks?.as_of ?? {}} />
      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {!stocks && !error && <p className="text-slate-500">Loading market data…</p>}
      {loading && (
        <p className="rounded border bg-white p-3 text-sm text-slate-600">
          Downloading the stock list and closing prices from NSE, BSE and Upstox. This takes about a minute on first run…
        </p>
      )}
      {stocks && stocks.count > 0 && (
        <>
          <IndexTiles tiles={tiles} ticks={ticks} />
          <Movers rows={rows} />
          <StockTable rows={rows} />
        </>
      )}
    </div>
  );
}
