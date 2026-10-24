import type { Metadata } from "next";
import Image from "next/image";
import { empresa } from "@/lib/empresa";
import { Chat } from "./chat";

export const metadata: Metadata = { alternates: { canonical: "/" } };

const pasos = [
  {
    titulo: "Dile qué quieres comprar",
    texto: "Escribe el nombre del producto y la zona. Si te falta algo, Prais te pregunta.",
  },
  {
    titulo: "Prais revisa las tiendas",
    texto: "Busca el mismo producto en tiendas web, redes sociales, Marketplace y Mercado Libre.",
  },
  {
    titulo: "Recibe la lista ordenada",
    texto: "Cada precio va con su fuente y su fecha, en dólares y en bolívares con la tasa usada, y con la confianza del comercio.",
  },
];

const canales = [
  { nombre: "Web", texto: "Aquí mismo: escribe lo que buscas en el chat de arriba." },
  { nombre: "WhatsApp", texto: `Escríbele a Prais al ${empresa.telefono} y te responde en el mismo chat.` },
  { nombre: "ChatGPT y Claude", texto: "Tu asistente de IA puede consultar a usaprais por MCP en usaprais.com/api/mcp." },
];

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "usaprais",
    legalName: empresa.razonSocial,
    url: empresa.sitio,
    email: empresa.correo,
    telephone: empresa.telefono,
    logo: `${empresa.sitio}/prais/prais-tranqui-circulo.svg`,
  },
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "usaprais",
    url: empresa.sitio,
    inLanguage: "es-VE",
  },
];

export default function Home() {
  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />

      <section className="overflow-hidden border-b-[2.5px] border-trazo bg-kraft">
        <div className="mx-auto grid max-w-5xl items-center gap-8 px-4 pt-12 pb-14 md:grid-cols-[1.4fr_0.6fr]">
          <div className="flex min-w-0 flex-col gap-5">
            <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-[1.03] uppercase">
              ¿Ese es el mejor <span className="text-tomate-texto">precio</span>? Prais te dice.
            </h1>
            <p className="max-w-[38ch] text-lg">
              El mismo producto puede costar muy distinto según dónde lo compres. Dile a Prais qué buscas: revisa los
              principales canales de venta de Venezuela y te dice dónde está el mejor precio.
            </p>
            <Chat />
          </div>
          <div className="relative mx-auto w-[min(70%,260px)] md:w-full md:max-w-[280px]">
            <Image
              src="/prais/prais-ganga-circulo.svg"
              alt="Prais, el asistente de usaprais, sonriendo porque encontró una ganga"
              width={280}
              height={280}
              priority
              unoptimized
              className="h-auto w-full"
            />
            <span className="sticker top-[4%] -left-[8%] -rotate-5 bg-sol text-on-sol">El más barato</span>
            <span className="sticker right-[-6%] bottom-[6%] rotate-4">$ y Bs.</span>
          </div>
        </div>
      </section>

      <section id="como-funciona" className="border-b border-linea">
        <div className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-16">
          <div className="flex max-w-[60ch] flex-col gap-2">
            <span className="text-[13px] font-medium tracking-wider text-tinta-suave uppercase">Cómo funciona</span>
            <h2 className="text-3xl font-semibold">Comparar precios toma un mensaje, no una tarde</h2>
          </div>
          <ol className="grid gap-6 md:grid-cols-3">
            {pasos.map((paso, index) => (
              <li key={paso.titulo} className="flex flex-col gap-2 border-t-[2.5px] border-tinta pt-4">
                <span className="text-[13px] font-medium tracking-wider text-tinta-suave uppercase">Paso {index + 1}</span>
                <h3 className="text-xl font-semibold">{paso.titulo}</h3>
                <p className="text-tinta-suave">{paso.texto}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-b border-linea">
        <div className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-16">
          <div className="flex max-w-[60ch] flex-col gap-2">
            <span className="text-[13px] font-medium tracking-wider text-tinta-suave uppercase">Dónde usarlo</span>
            <h2 className="text-3xl font-semibold">Prais responde donde ya estás</h2>
          </div>
          <div className="grid overflow-hidden rounded-[12px] border border-linea md:grid-cols-3">
            {canales.map((canal) => (
              <div
                key={canal.nombre}
                className="flex flex-col gap-1.5 border-b border-linea p-5 last:border-0 md:border-r md:border-b-0"
              >
                <h3 className="text-lg font-semibold">{canal.nombre}</h3>
                <p className="text-[15px] text-tinta-suave">{canal.texto}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-x-8 gap-y-4 rounded-[12px] bg-papel-bajo p-5">
            <p className="min-w-0 flex-[1_1_320px]">
              Prais solo te escribe por WhatsApp para responder lo que le preguntaste. No envía publicidad. Escribe{" "}
              <strong>BAJA</strong> en cualquier momento para dejar de recibir mensajes.
            </p>
            <a href={empresa.whatsapp} className="btn-cartel">
              Escríbele a Prais por WhatsApp
            </a>
          </div>
        </div>
      </section>

      <section id="empresa">
        <div className="mx-auto grid max-w-5xl gap-10 px-4 py-16 md:grid-cols-2">
          <div className="flex max-w-[60ch] flex-col gap-2">
            <span className="text-[13px] font-medium tracking-wider text-tinta-suave uppercase">Empresa</span>
            <h2 className="text-3xl font-semibold">Quién está detrás de usaprais</h2>
            <p className="mt-2 text-tinta-suave">
              usaprais es un servicio de comparación de precios para consumidores en Venezuela. No vende productos, no
              procesa pagos y no cobra a las tiendas por aparecer: muestra precios públicos y enlaza a la publicación
              original. usaprais es un servicio de {empresa.razonSocial}.
            </p>
          </div>
          <dl className="overflow-hidden rounded-[12px] border border-linea bg-papel-alto">
            {[
              ["Razón social", empresa.razonSocial],
              ["Nombre comercial", empresa.marca],
              ["Correo", empresa.correo],
              ["Teléfono y WhatsApp", empresa.telefono],
              ["Sitio web", "usaprais.com"],
              ["Atiende a", "Consumidores en Venezuela"],
            ].map(([dato, valor]) => (
              <div
                key={dato}
                className="grid gap-0.5 border-b border-linea px-4 py-3 last:border-0 sm:grid-cols-[170px_1fr] sm:gap-3"
              >
                <dt className="text-sm text-tinta-suave">{dato}</dt>
                <dd className="break-words">{valor}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </main>
  );
}
