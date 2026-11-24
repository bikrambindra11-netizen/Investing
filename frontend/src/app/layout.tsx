import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Picker Portal",
  description: "Personal NSE/BSE screening tool (macro + micro). Not investment advice.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="border-b bg-white">
          <div className="mx-auto max-w-6xl px-4 py-3 font-semibold">Stock Picker Portal</div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500">
          Personal screening output only. Not investment advice.
        </footer>
      </body>
    </html>
  );
}
