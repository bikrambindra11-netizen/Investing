import { API_BASE, fmtAsOf, type MarketStatus } from "@/lib/api";

const SEGMENT_OPEN = new Set(["NORMAL_OPEN", "PRE_OPEN_START", "PRE_OPEN_END"]);

export function LiveBanner({ status, backendConnected, asOf }: {
  status: MarketStatus | null;
  backendConnected: boolean;
  asOf: Record<string, string | null>;
}) {
  const closeInfo = `Showing last close: NSE ${fmtAsOf(asOf.NSE ?? null)}, BSE ${fmtAsOf(asOf.BSE ?? null)} (exchange bhavcopy files).`;

  if (!backendConnected && !status) {
    return <Box tone="red">Backend not reachable at {API_BASE}. Start it with the command in the README.</Box>;
  }
  if (!status) return <Box tone="slate">Checking live feed…</Box>;

  const { state, message, last_tick_at } = status.live;
  const nse = status.segment_status["NSE_EQ"];
  const marketOpen = nse ? SEGMENT_OPEN.has(nse) : status.market_open_by_clock;

  if (state === "connected") {
    return (
      <Box tone="green">
        <b>Live</b> · Upstox feed · last tick {last_tick_at ? fmtAsOf(last_tick_at) : "waiting…"}
        {!marketOpen && " · Market closed: prices are the last traded values."}
      </Box>
    );
  }
  if (state === "connecting" || state === "reconnecting") {
    return <Box tone="slate">Connecting to Upstox… {message} {closeInfo}</Box>;
  }
  if (state === "off") {
    return <Box tone="slate">Live feed not started. {closeInfo}</Box>;
  }
  if (state === "needs_keys") {
    return (
      <Box tone="amber">
        <b>Live prices are off.</b> {closeInfo} To turn them on, add <code>UPSTOX_API_KEY</code> and{" "}
        <code>UPSTOX_API_SECRET</code> to <code>.env</code> and restart the backend (see README).
      </Box>
    );
  }
  // needs_login / token_rejected
  return (
    <Box tone="amber">
      <b>Live prices are off.</b> {message ?? "Upstox needs a fresh login each day."} {closeInfo}{" "}
      <a href={`${API_BASE}/auth/upstox/login`} className="ml-1 inline-block rounded bg-slate-900 px-3 py-1 text-white">
        Login with Upstox
      </a>
    </Box>
  );
}

function Box({ tone, children }: { tone: "red" | "amber" | "green" | "slate"; children: React.ReactNode }) {
  const cls = {
    red: "border-red-300 bg-red-50 text-red-900",
    amber: "border-amber-300 bg-amber-50 text-amber-900",
    green: "border-green-300 bg-green-50 text-green-900",
    slate: "border-slate-200 bg-white text-slate-700",
  }[tone];
  return <div className={`rounded border p-3 text-sm ${cls}`}>{children}</div>;
}
