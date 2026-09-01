import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "HawkFundOS",
  description: "Hawk Fund investment intelligence platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
