import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { esRedireccion, getProducto, getRutas, SIN_DATOS } from "@/lib/catalogo";
import { empresa } from "@/lib/empresa";
import { bs, fecha, usd } from "@/lib/formato";
import { AvisoDemo, JsonLd, Migas, NotaTasa, Precio, PraisDice, Preguntas, Tarjetas } from "../../ui";
import { Ofertas } from "./ofertas";

// Ficha de producto: docs/ficha-producto.md.
export async function generateStaticParams() {
  const { productos } = await getRutas();
  return productos.length ? productos.map((producto) => ({ producto })) : [{ producto: SIN_DATOS }];
}

async function cargar(producto: string) {
  if (producto === SIN_DATOS) return null;
  return getProducto(producto);
}

export async function generateMetadata({ params }: PageProps<"/ve/p/[producto]">): Promise<Metadata> {
  const data = await cargar((await params).producto);
  if (!data || esRedireccion(data)) return {};
  const { producto: p, resumen: r } = data;
  const desde = r.nuevoDesde ?? r.usadoDesde;
  const title = desde
    ? `${p.nombre}: precio en Venezuela hoy desde ${usd(desde)}${r.nuevoDesdeBs ? ` (${bs(r.nuevoDesdeBs)})` : ""}`
    : `${p.nombre}: precio en Venezuela`;
  const description = `Compara el ${p.nombre} en ${r.comercios} comercios de Venezuela.${r.nuevoDesde ? ` Nuevo desde ${usd(r.nuevoDesde)}.` : ""}${r.usadoDesde ? ` Usado desde ${usd(r.usadoDesde)}.` : ""} Precios en dólares y bolívares, con la tasa usada.`;
  return {
    title,
    description,
    alternates: { canonical: p.url },
    openGraph: { title, description, url: p.url },
    robots: data.indexable ? undefined : { index: false, follow: true },
  };
}

export default async function Page({ params }: PageProps<"/ve/p/[producto]">) {
  const data = await cargar((await params).producto);
  if (!data) notFound();
  if (esRedireccion(data)) permanentRedirect(data.redirect);
  const { producto: p, resumen: r, tasa } = data;
  const nuevas = data.ofertas.filter((o) => o.condicion === "nuevo" && o.usd !== null);

  const preguntas = [
    r.nuevoDesde !== null && {
      pregunta: `¿Cuánto cuesta el ${p.nombre} en Venezuela?`,
      respuesta: `Nuevo, desde ${usd(r.nuevoDesde)}${r.nuevoDesdeBs ? ` (${bs(r.nuevoDesdeBs)} a la ${tasa.fuente})` : ""} en ${r.nuevoDesdeComercio}, visto el ${fecha(r.actualizado)}.${r.nuevoHasta && r.nuevoHasta !== r.nuevoDesde ? ` El más caro de los nuevos está en ${usd(r.nuevoHasta)}.` : ""}`,
    },
    r.nuevoDesde !== null && {
      pregunta: "¿Cuánto es en bolívares?",
      respuesta: `${r.nuevoDesdeBs ? bs(r.nuevoDesdeBs) : "—"} a la ${tasa.fuente} de ${bs(tasa.usdToVes)} por dólar (${fecha(tasa.fecha)}). El monto cambia con la tasa del día.`,
    },
    r.usadoDesde !== null && {
      pregunta: `¿Cuánto cuesta el ${p.nombre} usado?`,
      respuesta: `Desde ${usd(r.usadoDesde)}.${r.reacondicionadoDesde ? ` Reacondicionado, desde ${usd(r.reacondicionadoDesde)}.` : ""}`,
    },
    {
      pregunta: `¿Dónde comprar el ${p.nombre}?`,
      respuesta: `${r.comercios} comercios lo tienen publicado: ${[...new Set(data.ofertas.map((o) => o.comercio))].join(", ")}.`,
    },
  ].filter((x): x is { pregunta: string; respuesta: string } => Boolean(x));

  // Product con AggregateOffer solo con datos reales: nunca publicamos precios de ejemplo en schema.
  const producto = data.indexable &&
    r.nuevoDesde !== null && {
      "@context": "https://schema.org",
      "@type": "Product",
      name: p.nombre,
      brand: { "@type": "Brand", name: p.marca.nombre },
      category: p.categoria.nombre,
      url: `${empresa.sitio}${p.url}`,
      offers: {
        "@type": "AggregateOffer",
        priceCurrency: "USD",
        lowPrice: r.nuevoDesde,
        highPrice: r.nuevoHasta ?? r.nuevoDesde,
        offerCount: nuevas.length,
        itemCondition: "https://schema.org/NewCondition",
      },
    };

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8">
      {producto && <JsonLd data={producto} />}
      <Migas
        items={[
          { nombre: "Inicio", url: "/" },
          { nombre: p.categoria.nombre, url: p.categoria.url },
          { nombre: p.marca.nombre, url: p.marca.url },
          { nombre: p.nombre, url: p.url },
        ]}
      />
      <AvisoDemo visible={data.datosDeEjemplo} />

      <section className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <h1 className="text-[clamp(28px,5vw,36px)] leading-tight font-semibold">{p.nombre}</h1>
          <p className="text-[15px] text-tinta-suave">
            {r.nuevoDesde !== null ? `Desde ${usd(r.nuevoDesde)} en ${r.comercios} comercios` : `En ${r.comercios} comercios`}
            {r.actualizado ? ` · Visto el ${fecha(r.actualizado)}` : ""} · {tasa.fuente}: {bs(tasa.usdToVes)}
          </p>
        </div>
        {r.nuevoDesde !== null && (
          <PraisDice animo="ganga">
            El {p.nombre} cuesta desde <b>{usd(r.nuevoDesde)}</b> nuevo en Venezuela, visto el {fecha(r.actualizado)} en{" "}
            {r.nuevoDesdeComercio}.{r.usadoDesde !== null && <> Usado, desde <b>{usd(r.usadoDesde)}</b>.</>}
          </PraisDice>
        )}
        <div className="flex flex-wrap items-end gap-x-8 gap-y-5 rounded-[12px] border border-linea bg-papel-alto p-5">
          {r.nuevoDesde !== null && <Precio valor={r.nuevoDesde} enBs={r.nuevoDesdeBs} etiqueta="Nuevo desde" grande />}
          <dl className="grid flex-[1_1_260px] grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {r.usadoDesde !== null && (
              <div>
                <dt className="text-tinta-suave">Usado desde</dt>
                <dd className="font-semibold tabular-nums">{usd(r.usadoDesde)}</dd>
              </div>
            )}
            {r.reacondicionadoDesde !== null && (
              <div>
                <dt className="text-tinta-suave">Reacondicionado desde</dt>
                <dd className="font-semibold tabular-nums">{usd(r.reacondicionadoDesde)}</dd>
              </div>
            )}
            {r.nuevoDesde !== null && r.nuevoHasta !== null && (
              <div>
                <dt className="text-tinta-suave">Rango nuevo</dt>
                <dd className="font-semibold tabular-nums">
                  {usd(r.nuevoDesde)} – {usd(r.nuevoHasta)}
                </dd>
              </div>
            )}
            <div>
              <dt className="text-tinta-suave">Comercios</dt>
              <dd className="font-semibold">{r.comercios}</dd>
            </div>
          </dl>
        </div>
      </section>

      <Ofertas ofertas={data.ofertas} />
      <NotaTasa tasa={tasa} actualizado={r.actualizado} />

      {data.variantes.length > 1 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-2xl font-semibold">Variantes</h2>
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
            {data.variantes.map((v) => (
              <li key={v.nombre} className="flex flex-col gap-1 rounded-[12px] border border-linea bg-papel-alto p-4">
                <span className="font-medium">{v.nombre}</span>
                <span className="text-sm text-tinta-suave tabular-nums">Nuevo desde {usd(v.desde)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.alternativas.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-2xl font-semibold">Alternativas en ese rango</h2>
          <Tarjetas items={data.alternativas} />
        </section>
      )}

      <Preguntas items={preguntas} conJsonLd={data.indexable} />

      <nav aria-label="Más" className="flex flex-wrap gap-x-5 gap-y-2 border-t border-linea pt-6 text-[15px]">
        <Link href={p.categoria.url} className="text-anil underline underline-offset-2">
          Todos los {p.categoria.nombre.toLowerCase()}
        </Link>
        <Link href={p.marca.url} className="text-anil underline underline-offset-2">
          Más de {p.marca.nombre}
        </Link>
      </nav>
    </main>
  );
}
