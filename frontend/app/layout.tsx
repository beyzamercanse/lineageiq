import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "LineageIQ",
  description:
    "Evidence-grounded data-incident investigation for the synthetic company AtlasCommerce.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/incidents", label: "Incidents" },
  { href: "/lineage", label: "Lineage" },
  { href: "/evaluation", label: "Evaluation" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav className="nav">
          <span className="brand">LineageIQ</span>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}>
              {n.label}
            </Link>
          ))}
          <span style={{ marginLeft: "auto" }} className="muted">
            synthetic data · portfolio system
          </span>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
