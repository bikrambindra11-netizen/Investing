import type { Metadata } from "next";
import Link from "next/link";
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
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-1 px-4 py-3">
            <Link href="/" className="font-semibold">Stock Picker Portal</Link>
            <Link href="/" className="text-sm text-slate-600 hover:text-slate-900">Market</Link>
            <Link href="/industries" className="text-sm text-slate-600 hover:text-slate-900">Industries</Link>
            <Link href="/economy" className="text-sm text-slate-600 hover:text-slate-900">Economy</Link>
            <Link href="/setup" className="ml-auto text-sm text-slate-600 hover:text-slate-900">Setup</Link>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500">
          Personal screening output only. Not investment advice.
        </footer>
      </body>
    </html>
  );
}
