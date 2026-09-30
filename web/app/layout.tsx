import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cogito — MongoDB RAG Knowledge Assistant",
  description:
    "A self-indexing MongoDB-native RAG knowledge base, exposed as an MCP server.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}