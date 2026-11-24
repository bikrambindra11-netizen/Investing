export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type Health = {
  status: string;
  time: string;
  database: string;
  instruments: number;
  keys_configured: Record<string, boolean>;
  disclaimer: string;
};
