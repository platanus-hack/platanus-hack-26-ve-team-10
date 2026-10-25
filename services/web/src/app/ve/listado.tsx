import type { Metadata } from "next";
import Link from "next/link";
import type { PaginaCategoria } from "@/lib/catalogo";
import { empresa } from "@/lib/empresa";
import { bs, fecha, usd } from "@/lib/formato";
import { AvisoDemo, JsonLd, Migas, NotaTasa, PraisDice, Preguntas, Tarjetas } from "./ui";

// Categoría, categoría + marca y faceta comparten plantilla: docs/categoria.md.

export function metadataDeListado(data: PaginaCategoria): Metadata {
  const { titulo, resumen: r } = data;
  const title = r.desde ? `${titulo} en Venezuela: precios hoy desde ${usd(r.desde)}` : `${titulo} en Venezuela: precios hoy`;
  const description = `Compara ${r.modelos} modelos de ${titulo.toLowerCase()} en ${r.comercios ?? 0} comercios de Venezuela${r.desde ? `, desde ${usd(r.desde)}` : ""}. Precios en dólares y bolívares, con la tasa usada.`;
  return {
    title,
    description,
    alternates: { canonical: data.url },
    openGraph: { title, description, url: data.url },
    robots: data.indexable ? undefined : { index: false, follow: true },
  };
}

export function Listado({ data }: { data: PaginaCategoria }) {
  const { categoria: c, resumen: r, tasa } = data;
  const migas = [
    { nombre: "Inicio", url: "/" },
    { nombre: c.nombre, url: c.url },
    ...(data.tipo === "categoria" ? [] : [{ nombre: data.marca?.nombre ?? data.faceta?.nombre ?? "", url: data.url }]),
  ];
  const sujeto = data.titulo.toLowerCase();
  const preguntas = [
    r.masBarato && {
      pregunta: `¿Cuál es el ${data.marca ? `${c.singular} ${data.marca.nombre}` : c.singular} más barato en Venezuela?`,
      respuesta: `${r.masBarato.nombre}, desde ${usd(r.masBarato.usd)}${r.desdeBs ? ` (${bs(r.desdeBs)})` : ""}. Precio visto el ${fecha(r.actualizado)}.`,
    },
    r.masBuscado && {
      pregunta: `¿Cuál es el ${data.marca ? `${c.singular} ${data.marca.nombre}` : c.singular} más buscado?`,
      respuesta: `${r.masBuscado.nombre}.`,
    },
    {
      pregunta: `¿Dónde comprar ${sujeto} en Venezuela?`,
      respuesta: `${r.comercios ?? 0} comercios tienen ${sujeto} publicados. En cada ficha ves sus precios, su ciudad y si hacen envíos.`,
    },
  ].filter((x): x is { pregunta: string; respuesta: string } => Boolean(x));

  const lista = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    itemListElement: data.productos.map((t, i) => ({ "@type": "ListItem", position: i + 1, url: `${empresa.sitio}${t.url}` })),
  };

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8">
      <JsonLd data={lista} />
      <Migas items={migas} />
      <AvisoDemo visible={data.datosDeEjemplo} />

      <div className="flex max-w-[760px] flex-col gap-4">
        <h1 className="text-[clamp(28px,5vw,36px)] leading-tight font-semibold">{data.titulo}</h1>
        {r.desde && (
          <PraisDice animo="tranqui">
            Hay <b>{r.modelos} modelos</b> de {sujeto} en {r.comercios} comercios de Venezuela, desde <b>{usd(r.desde)}</b>
            {r.desdeBs ? ` (${bs(r.desdeBs)})` : ""}.{r.masBuscado && <> El más buscado es el {r.masBuscado.nombre}</>}
            {r.masBarato && <>; el más barato, el {r.masBarato.nombre}</>}. Precios vistos el {fecha(r.actualizado)}.
          </PraisDice>
        )}
      </div>

      {data.series.length > 1 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[15px] font-semibold">Series</h2>
          <ul className="flex flex-wrap gap-2">
            {data.series.map((s) => (
              <li key={s.nombre} className="rounded-full border border-borde bg-papel-alto px-4 py-2 text-[15px] font-medium">
                {s.nombre} <span className="text-[13px] font-normal text-tinta-suave">{s.modelos}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.tipo !== "marca" && data.marcas.length > 1 && (
        <nav aria-label="Marcas" className="flex flex-col gap-3">
          <h2 className="text-[15px] font-semibold">Marcas</h2>
          <ul className="flex flex-wrap gap-2">
            {data.marcas.map((m) => (
              <li key={m.slug}>
                <Link
                  href={m.url}
                  className="inline-flex min-h-11 items-center gap-2 rounded-full border border-borde bg-papel-alto px-4 text-[15px] font-medium hover:bg-papel-bajo"
                >
                  {m.nombre} <span className="text-[13px] font-normal text-tinta-suave">{m.modelos}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}

      <section aria-labelledby="lista-h" className="flex flex-col gap-4">
        <h2 id="lista-h" className="text-[15px] font-medium text-tinta-suave">
          {r.modelos} modelos · ordenados por los más buscados
        </h2>
        <Tarjetas items={data.productos} />
        <NotaTasa tasa={tasa} actualizado={r.actualizado} />
      </section>

      {(data.facetas.length > 0 || data.tipo !== "categoria") && (
        <nav aria-label="Relacionadas" className="flex flex-col gap-3 rounded-[12px] bg-papel-bajo p-6">
          <h2 className="text-lg font-semibold">Relacionadas</h2>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-[15px]">
            {data.facetas
              .filter((f) => f.url !== data.url)
              .map((f) => (
                <Link key={f.url} href={f.url} className="text-anil underline underline-offset-2">
                  {f.nombre}
                </Link>
              ))}
            {data.tipo !== "categoria" && (
              <Link href={c.url} className="text-anil underline underline-offset-2">
                Todos los {c.nombre.toLowerCase()}
              </Link>
            )}
            {data.tipo === "marca" && data.marca && (
              <Link href={data.marca.url} className="text-anil underline underline-offset-2">
                Todo {data.marca.nombre}
              </Link>
            )}
          </div>
        </nav>
      )}

      <Preguntas items={preguntas} conJsonLd={data.indexable} />
    </main>
  );
}
