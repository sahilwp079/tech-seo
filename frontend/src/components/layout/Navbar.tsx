"use client";
import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="bg-white border-b px-6 py-3 flex items-center justify-between sticky top-0 z-50 shadow-sm">
      <Link href="/dashboard" className="text-lg font-bold text-blue-600 tracking-tight">
        SEO Audit Agent
      </Link>
      <div className="flex items-center gap-4">
        <Link href="/dashboard" className="text-sm text-gray-600 hover:text-blue-600 transition">
          Dashboard
        </Link>
        <Link
          href="/audit/new"
          className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 transition"
        >
          + New Audit
        </Link>
      </div>
    </nav>
  );
}
