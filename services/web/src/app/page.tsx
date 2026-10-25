import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { esRedireccion, getProducto, getRutas, type PaginaProducto } from "@/lib/catalogo";
import { empresa, whatsappPrais } from "@/lib/empresa";
import { bs, CANALES, fecha, usd } from "@/lib/formato";
import { Chat } from "./chat";
import { Icono } from "./icono";

export const metadata: Metadata = { alternates: { canonical: "/" } };

const promesas = [
  {
    icono: "tienda",
    titulo: "No vende nada",
    texto: "usaprais no tiene tiendas favoritas ni cobra a nadie por aparecer. Enlaza a la publicación original.",
  },
  {
    icono: "reloj",
    titulo: "Cada precio con fuente y fecha",
    texto: "Ves de dónde salió cada precio y cuándo se revisó. Si se convirtió de bolívares, también la tasa usada.",
  },
  {
    icono: null,
    titulo: "Dólares primero, bolívares siempre",
    texto: "Cada precio en dólares lleva su equivalente en Bs. debajo, con la tasa a la vista.",
  },
  {
    icono: "escudo",
    titulo: "Te dice si el vendedor es dudoso",
    texto: "Cada comercio lleva su nivel de confianza. Si el más barato tiene pocas referencias, Prais te lo dice.",
  },
] as const;

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "usaprais",
    alternateName: ["usa prais", "usaprice", "usaprices", "Prais"],
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

// La muestra del hero es una ficha real del catálogo (el producto más buscado), con su fuente,
// su fecha y su tasa. Si la API no responde, el hero muestra a Prais solo.
async function muestra() {
  const { productos } = await getRutas();
  if (!productos.length) return null;
  const data = await getProducto(productos[0]).catch(() => null);
  return data && !esRedireccion(data) ? data : null;
}

export default async function Home() {
  const data = await muestra();
  const filas = data?.ofertas.filter((o) => o.condicion === "nuevo" && o.usd !== null).slice(0, 3) ?? [];

  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />

      <section className="grano overflow-hidden border-b-[2.5px] border-trazo bg-kraft">
        <div className="mx-auto grid max-w-6xl items-center gap-x-14 gap-y-12 px-4 pt-12 pb-20 md:pt-16 md:pb-24 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="flex min-w-0 flex-col gap-6">
            <h1 className="font-display text-[clamp(34px,6.2vw,64px)] leading-[1.02] uppercase">
              ¿Ese es el mejor{" "}
              <span className="whitespace-nowrap">
                <span className="relative inline-block text-tomate-texto">
                precio
                <svg
                  viewBox="0 0 200 20"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                  className="absolute -bottom-[0.14em] left-0 h-[0.22em] w-full overflow-visible"
                >
                  <path
                    d="M3 13 C 50 5, 120 4, 197 10"
                    pathLength={1}
                    fill="none"
                    stroke="var(--sol)"
                    strokeWidth={7}
                    strokeLinecap="round"
                    className="marcador"
                  />
                </svg>
                </span>
                ?
              </span>{" "}
              Prais te dice.
            </h1>
            <p className="max-w-[44ch] text-lg leading-relaxed">
              El mismo producto cuesta distinto en Instagram, Marketplace, Mercado Libre y las tiendas web. Dile a Prais
              qué buscas y te dice dónde está más barato, en dólares y en bolívares.
            </p>
            <Chat />
          </div>

          {data && filas.length > 0 ? <Muestra data={data} filas={filas} /> : <PraisSolo />}
        </div>
      </section>

      <section id="como-funciona" className="scroll-mt-4 border-b border-linea">
        <div className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-20">
          <Encabezado kicker="Cómo funciona" titulo="Comparar precios toma un mensaje, no una tarde" />
          <ol className="grid gap-8 md:grid-cols-3 md:gap-6">
            <Paso n={1} titulo="Dile qué quieres comprar" texto="Escribe el producto y, si quieres, tu ciudad. Si falta un dato, Prais te pregunta.">
              <p className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-accion px-4 py-2 text-on-accion">
                {data?.producto.nombre ?? "iPhone 15"} en Caracas
              </p>
              <p className="max-w-[85%] self-start rounded-2xl rounded-tl-md bg-papel-alto px-4 py-2 text-[15px] text-tinta-suave">
                ¿Nuevo o usado?
              </p>
            </Paso>
            <Paso
              n={2}
              titulo="Prais revisa las tiendas"
              texto="Busca el mismo producto en tiendas web, redes sociales, Marketplace y Mercado Libre."
            >
              <ul className="flex flex-wrap justify-center gap-2">
                {["Instagram", "Mercado Libre", "Marketplace", "Tiendas web", "TikTok"].map((canal) => (
                  <li
                    key={canal}
                    className="flex items-center gap-1.5 rounded-full border border-linea bg-papel-alto py-1.5 pr-3 pl-2 text-[15px]"
                  >
                    <Icono nombre="check" size={16} className="text-ahorro" />
                    {canal}
                  </li>
                ))}
              </ul>
            </Paso>
            <Paso
              n={3}
              titulo="Recibe la lista ordenada"
              texto="Del más barato al más caro, con la fuente, la fecha y la confianza de cada comercio."
            >
              <ol className="w-full overflow-hidden rounded-[10px] border border-linea bg-papel-alto text-[15px]">
                {(filas.length ? filas : [null, null, null]).map((o, i) => (
                  <li
                    key={i}
                    className={`flex items-center gap-3 border-t border-linea px-3 py-2 first:border-t-0 ${i === 0 ? "bg-sol-tinte" : ""}`}
                  >
                    <span className="w-3 text-tinta-suave tabular-nums">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate">{o?.comercio ?? <Hueco />}</span>
                    <span className="font-semibold tabular-nums">{o?.usd != null ? usd(o.usd) : <Hueco ancho="w-10" />}</span>
                  </li>
                ))}
              </ol>
            </Paso>
          </ol>
        </div>
      </section>

      <section id="donde-usarlo" className="scroll-mt-4 border-b border-linea">
        <div className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-20">
          <Encabezado kicker="Dónde usarlo" titulo="Prais responde donde ya estás" />
          <div className="grid gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-3 rounded-[14px] border border-linea bg-papel-alto p-6">
              <h3 className="text-xl font-semibold">En la web</h3>
              <p className="text-tinta-suave">Escribe lo que buscas en el buscador de arriba y Prais te responde aquí mismo.</p>
              <a href="#buscar" className="mt-auto inline-flex items-center gap-1.5 pt-2 font-medium text-anil hover:underline">
                Ir al buscador
                <Icono nombre="flecha" size={18} className="-rotate-90" />
              </a>
            </div>
            <div className="grano flex flex-col gap-3 rounded-[14px] border-[2.5px] border-trazo bg-kraft p-6 shadow-[var(--sombra-cartel)]">
              <h3 className="text-xl font-semibold">Por WhatsApp</h3>
              <p>Escríbele a Prais al {empresa.telefono} y te responde en el mismo chat, con los precios en una lista.</p>
              <a href={whatsappPrais} className="btn-cartel mt-auto self-start">
                Escríbele a Prais
                <Icono nombre="flecha" size={18} />
              </a>
            </div>
            <div className="flex flex-col gap-3 rounded-[14px] border border-linea bg-papel-alto p-6">
              <h3 className="text-xl font-semibold">En ChatGPT y Claude</h3>
              <p className="text-tinta-suave">Tu asistente de IA puede consultar a usaprais como herramienta MCP.</p>
              <code className="mt-auto self-start rounded-[8px] bg-papel-bajo px-3 py-2 font-mono text-[14px]">
                usaprais.com/api/mcp
              </code>
            </div>
          </div>
          <p className="flex items-start gap-2 text-[15px] text-tinta-suave">
            <Icono nombre="escudo" size={18} className="mt-0.5" />
            <span>
              Prais solo te escribe por WhatsApp para responder lo que le preguntaste. No envía publicidad. Escribe{" "}
              <strong className="text-tinta">BAJA</strong> en cualquier momento para dejar de recibir mensajes.
            </span>
          </p>
        </div>
      </section>

      <section id="de-tu-lado" className="scroll-mt-4 bg-trazo text-kraft">
        <div className="mx-auto flex max-w-6xl flex-col gap-12 px-4 py-20">
          <div className="flex max-w-[60ch] flex-col gap-2">
            <span className="text-[13px] font-medium tracking-wider text-sol uppercase">De tu lado</span>
            <h2 className="text-3xl font-semibold md:text-4xl">Prais trabaja para ti, no para las tiendas</h2>
          </div>
          <ul className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
            {promesas.map((p) => (
              <li key={p.titulo} className="flex flex-col gap-3">
                <span className="flex size-11 items-center justify-center rounded-[10px] bg-sol text-on-sol">
                  {p.icono ? <Icono nombre={p.icono} size={22} /> : <span className="text-xl font-bold">$</span>}
                </span>
                <h3 className="text-lg font-semibold">{p.titulo}</h3>
                <p className="text-kraft/75">{p.texto}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}

function Encabezado({ kicker, titulo }: { kicker: string; titulo: string }) {
  return (
    <div className="flex max-w-[60ch] flex-col gap-2">
      <span className="text-[13px] font-medium tracking-wider text-tinta-suave uppercase">{kicker}</span>
      <h2 className="text-3xl font-semibold md:text-4xl">{titulo}</h2>
    </div>
  );
}

function Paso({ n, titulo, texto, children }: { n: number; titulo: string; texto: string; children: React.ReactNode }) {
  return (
    <li className="flex min-w-0 flex-col gap-4">
      <div className="flex h-44 flex-col justify-center gap-2 rounded-[14px] bg-papel-bajo p-5">{children}</div>
      <div className="flex flex-col gap-1.5">
        <span className="text-[13px] font-medium tracking-wider text-tinta-suave uppercase">Paso {n}</span>
        <h3 className="text-xl font-semibold">{titulo}</h3>
        <p className="text-tinta-suave">{texto}</p>
      </div>
    </li>
  );
}

function Hueco({ ancho = "w-24" }: { ancho?: string }) {
  return <span className={`inline-block h-2.5 rounded-full bg-linea align-middle ${ancho}`} />;
}

// Capa de producto (sobria) dentro del hero de marca: la tarjeta va derecha y los stickers la rodean.
function Muestra({ data, filas }: { data: PaginaProducto; filas: PaginaProducto["ofertas"] }) {
  const { producto: p, resumen: r, tasa } = data;
  const nuevas = data.ofertas.filter((o) => o.condicion === "nuevo").length;

  return (
    <figure className="relative mx-auto w-full max-w-[520px] pt-8 pl-4 sm:pl-8">
      <Image
        src="/prais/prais-ganga-circulo.svg"
        alt="Prais, el asistente de usaprais, contento porque encontró un buen precio"
        width={88}
        height={88}
        priority
        unoptimized
        className="entra absolute top-0 left-0 z-10 size-[72px] sm:size-[88px]"
      />
      <div className="entra overflow-hidden rounded-[16px] border-[2.5px] border-trazo bg-papel-alto shadow-[var(--sombra-cartel)]">
        <figcaption className="flex flex-col gap-1 border-b border-linea py-4 pr-4 pl-[68px] sm:pl-[76px]">
          <p className="text-[17px] leading-snug">
            Revisé {r.comercios} comercios. El {p.nombre} nuevo está desde <b>{usd(r.nuevoDesde ?? filas[0].usd!)}</b>.
          </p>
          <p className="text-[13px] text-tinta-suave">
            {nuevas} precios · del más barato al más caro · {tasa.fuente}: {bs(tasa.usdToVes)}
          </p>
        </figcaption>
        <ol>
          {filas.map((o, i) => (
            <li
              key={`${o.comercio}-${o.url}`}
              style={{ "--i": i + 2 } as React.CSSProperties}
              className={`entra grid grid-cols-[16px_1fr_auto] items-start gap-x-3 border-t border-linea px-4 py-3.5 first:border-t-0 ${i === 0 ? "bg-sol-tinte" : ""}`}
            >
              <span className="pt-0.5 text-[15px] font-semibold text-tinta-suave tabular-nums">{i + 1}</span>
              <div className="flex min-w-0 flex-col gap-1">
                {i === 0 && (
                  <span className="self-start rounded-[6px] bg-sol px-2 py-0.5 text-[13px] font-medium text-on-sol">Más barato</span>
                )}
                <p className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-medium">{o.comercio}</span>
                  <span className="text-[13px] text-tinta-suave">{CANALES[o.canal] ?? o.canal}</span>
                </p>
                <p className="text-[13px] text-tinta-suave">
                  {[o.variante, o.zona, o.envia ? "envío nacional" : "retiro en persona"].filter(Boolean).join(" · ")}
                </p>
                <p className={`flex items-center gap-1.5 text-[13px] ${o.confianza < 50 ? "text-caro-texto" : "text-tinta-suave"}`}>
                  <Icono nombre={o.confianza < 50 ? "alerta" : "escudo"} size={14} />
                  {o.confianzaTexto}
                </p>
              </div>
              <p className="flex flex-col items-end tabular-nums">
                <span className="text-xl font-semibold">{usd(o.usd!)}</span>
                {o.bs !== null && <span className="text-[13px] whitespace-nowrap text-tinta-suave">{bs(o.bs)}</span>}
              </p>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-linea bg-papel-bajo px-4 py-3 text-[13px]">
          <span className="flex items-center gap-1.5 text-tinta-suave">
            <Icono nombre="reloj" size={14} />
            Visto el {fecha(r.actualizado)}
            {data.datosDeEjemplo && " · Datos de ejemplo"}
          </span>
          <Link href={p.url} className="inline-flex items-center gap-1 font-medium text-anil hover:underline">
            Ver los {nuevas} precios
            <Icono nombre="flecha" size={14} />
          </Link>
        </div>
      </div>
      <span
        style={{ "--retraso": "550ms" } as React.CSSProperties}
        className="sticker sticker-entra -top-1 right-0 -rotate-5 bg-sol text-on-sol sm:-right-4"
      >
        El más barato
      </span>
      <span
        style={{ "--retraso": "700ms" } as React.CSSProperties}
        className="sticker sticker-entra right-8 -bottom-8 rotate-4"
      >
        $ y Bs.
      </span>
    </figure>
  );
}

function PraisSolo() {
  return (
    <div className="relative mx-auto w-[min(70%,280px)]">
      <Image
        src="/prais/prais-ganga-circulo.svg"
        alt="Prais, el asistente de usaprais, sonriendo porque encontró una ganga"
        width={280}
        height={280}
        priority
        unoptimized
        className="h-auto w-full"
      />
      <span className="sticker sticker-entra top-[4%] -left-[8%] -rotate-5 bg-sol text-on-sol">El más barato</span>
      <span className="sticker sticker-entra right-[-6%] bottom-[6%] rotate-4">$ y Bs.</span>
    </div>
  );
}
