import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import Nav from "./Nav";
import { Analytics } from "@vercel/analytics/react";

export const metadata: Metadata = {
  title: "TRACER Sports",
  description:
    "Power ratings that trace team strength across every game, every season, since 1996.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <Suspense fallback={null}>
          <Nav />
        </Suspense>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
