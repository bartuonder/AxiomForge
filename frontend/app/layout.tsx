import type { Metadata } from "next";
import { Fraunces, Source_Sans_3 } from "next/font/google";
import { LanguageProvider } from "@/components/LanguageProvider";
import "./globals.css";

const display = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
});

const sans = Source_Sans_3({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AxiomForge",
  description: "Bir iddianın doğru olup olmadığını gerçek verilerle sınayın.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="tr" className={`${display.variable} ${sans.variable} h-full antialiased`}>
      <body className="min-h-full bg-[#f4f0e6] text-[#1c1915]">
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
