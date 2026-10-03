import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RailCast AI — Dynamic ETA Intelligence",
  description:
    "Don't just predict arrival. Forecast the journey of the delay. An explainable, continuously re-calculated ETA intelligence layer for coaching trains.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="sticky top-0 z-40 border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center">
              <span>
                <span className="block text-sm font-bold tracking-wide text-gray-900">
                  RailCast AI
                </span>
                <span className="block text-[10px] uppercase tracking-wider text-gray-500">
                  Dynamic Delay Trajectory &amp; ETA Intelligence
                </span>
              </span>
            </Link>
            <nav className="text-xs text-gray-500">
              <span className="hidden sm:inline">
                Train ETA Forecasting
              </span>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="border-t border-gray-200 py-4 text-center text-[11px] text-gray-500">
          RailCast AI prototype · Not a railway control system · Data shown is for
          demonstration purposes only
        </footer>
      </body>
    </html>
  );
}
