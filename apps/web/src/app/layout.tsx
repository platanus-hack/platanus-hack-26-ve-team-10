import type { Metadata } from "next";
import { Bungee, Outfit } from "next/font/google";
import Link from "next/link";
import { empresa } from "@/lib/empresa";
import "./globals.css";

const outfit = Outfit({ variable: "--font-outfit", subsets: ["latin"] });
const bungee = Bungee({ variable: "--font-bungee", subsets: ["latin"], weight: "400" });

export const metadata: Metadata = {
  metadataBase: new URL(empresa.sitio),
  title: {
    default: "usaprais: el mejor precio en Venezuela",
    template: "%s | usaprais",
  },
  description:
    "usaprais compara el precio de un producto en los principales canales de venta de Venezuela y te dice dónde comprarlo al mejor precio, en dólares y en bolívares.",
  openGraph: { siteName: "usaprais", locale: "es_VE", type: "website" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es-VE" className={`${outfit.variable} ${bungee.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="border-b-[2.5px] border-trazo bg-kraft">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
            <Link href="/" className="wordmark" aria-label="usaprais, inicio">
              usa<span>prais</span>
            </Link>
            <nav aria-label="Secciones" className="hidden gap-5 font-medium sm:flex">
              <Link href="/#como-funciona" className="hover:underline">
                Cómo funciona
              </Link>
              <Link href="/#empresa" className="hover:underline">
                Empresa
              </Link>
            </nav>
          </div>
        </header>
        {children}
        <footer className="mt-auto border-t-[2.5px] border-trazo bg-kraft">
          <div className="mx-auto grid max-w-5xl gap-8 px-4 py-10 text-[15px] sm:grid-cols-[1.2fr_1fr_1fr]">
            <div className="flex flex-col gap-3">
              <span className="wordmark" aria-label="usaprais">
                usa<span>prais</span>
              </span>
              <p className="text-tinta-suave">Compara el precio de un producto en las tiendas de Venezuela antes de comprar.</p>
            </div>
            <div className="flex flex-col gap-2">
              <strong>Contacto</strong>
              <span>{empresa.correo}</span>
              <span>{empresa.telefono}</span>
              <a href={empresa.whatsapp} className="underline underline-offset-2">
                WhatsApp
              </a>
            </div>
            <div className="flex flex-col gap-2">
              <strong>Legal</strong>
              <Link href="/privacidad" className="underline underline-offset-2">
                Política de privacidad
              </Link>
              <Link href="/terminos" className="underline underline-offset-2">
                Términos de uso
              </Link>
            </div>
            <p className="border-t border-trazo pt-5 text-[13px] text-tinta-suave sm:col-span-3">
              © 2026 {empresa.razonSocial}. usaprais es un servicio de {empresa.razonSocial}. No está afiliado a Meta,
              WhatsApp, Instagram ni Mercado Libre.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
