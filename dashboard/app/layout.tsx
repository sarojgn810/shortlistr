import type { Metadata } from "next";
import { Urbanist } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/src/providers/AppProviders";

const urbanist = Urbanist({
  variable: "--font-urbanist",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Shortlistr — Judgment-first job search",
    template: "%s | Shortlistr",
  },
  description:
    "Evaluate offers, track applications, and apply with human-in-the-loop judgment.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${urbanist.variable} antialiased bg-sage text-ink font-sans`}>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
