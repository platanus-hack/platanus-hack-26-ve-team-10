import type { Metadata } from "next";
import { Bungee, Outfit } from "next/font/google";
import Link from "next/link";
import { empresa, whatsappPrais } from "@/lib/empresa";
import { guias } from "@/lib/guias";
import "./globals.css";
import { Icono } from "./icono";

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

// Las secciones clave de la landing; desde otras páginas, el enlace vuelve a la landing.
const secciones = [
  { nombre: "Cómo funciona", href: "/#como-funciona" },
  { nombre: "Dónde usarlo", href: "/#donde-usarlo" },
  { nombre: "De tu lado", href: "/#de-tu-lado" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es-VE" className={`${outfit.variable} ${bungee.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="border-b-[2.5px] border-trazo bg-kraft">
          <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
            <Link href="/" className="wordmark mr-auto" aria-label="usaprais, inicio">
              usa<span>prais</span>
            </Link>
            <nav aria-label="Secciones" className="hidden items-center gap-1 font-medium md:flex">
              {secciones.map((s) => (
                <Link
                  key={s.href}
                  href={s.href}
                  className="rounded-[8px] px-3 py-2 transition-colors duration-150 hover:bg-trazo/[0.06]"
                >
                  {s.nombre}
                </Link>
              ))}
            </nav>
            <a href={whatsappPrais} className="btn-cartel px-4 py-2 text-[15px]">
              Escríbele a Prais
              <Icono nombre="flecha" size={16} />
            </a>
          </div>
        </header>
        {children}
        <footer className="mt-auto border-t-[2.5px] border-trazo bg-kraft">
          <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-[15px] sm:grid-cols-2 md:grid-cols-[1.2fr_1fr_1fr_1fr]">
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
              <a href={whatsappPrais} className="underline underline-offset-2">
                WhatsApp
              </a>
            </div>
            <div className="flex flex-col gap-2">
              <strong>Guías</strong>
              {guias.map((g) => (
                <Link key={g.slug} href={`/${g.slug}`} className="underline underline-offset-2">
                  {g.h1}
                </Link>
              ))}
              <Link href="/ve/marcas" className="underline underline-offset-2">
                Marcas y categorías
              </Link>
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
            <p className="border-t border-trazo pt-5 text-[13px] text-tinta-suave sm:col-span-2 md:col-span-4">
              © 2026 {empresa.razonSocial}. usaprais es un servicio de {empresa.razonSocial}. No está afiliado a Meta,
              WhatsApp, Instagram ni Mercado Libre.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
