import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SEO Audit Agent",
  description: "Technical SEO audit tool",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen font-sans">{children}</body>
    </html>
  );
}
