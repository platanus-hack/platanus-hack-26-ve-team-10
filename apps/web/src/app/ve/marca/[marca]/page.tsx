import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { esRedireccion, getMarca, getRutas, SIN_DATOS } from "@/lib/catalogo";
import { bs, fecha, usd } from "@/lib/formato";
import { AvisoDemo, Migas, NotaTasa, PraisDice, Preguntas, Tarjetas } from "../../ui";

// Página de marca: docs/marca.md. Una marca de una sola categoría redirige a su categoría + marca.
export async function generateStaticParams() {
  const { marcas } = await getRutas();
  return marcas.length ? marcas.map((marca) => ({ marca })) : [{ marca: SIN_DATOS }];
}

async function cargar(marca: string) {
  return marca === SIN_DATOS ? null : getMarca(marca);
}

export async function generateMetadata({ params }: PageProps<"/ve/marca/[marca]">): Promise<Metadata> {
  const data = await cargar((await params).marca);
  if (!data || esRedireccion(data)) return {};
  const r = data.resumen;
  const cats = data.categorias
    .slice(0, 2)
    .map((c) => c.nombre.replace(` ${data.marca.nombre}`, "").toLowerCase())
    .join(", ");
  const title = `${data.titulo}: precios de ${cats} y más${r.desde ? ` desde ${usd(r.desde)}` : ""}`;
  const description = `${data.marca.nombre} tiene ${r.modelos} modelos en ${r.categorias} categorías y ${r.comercios} comercios de Venezuela. Compara precios en dólares y bolívares.`;
  return {
    title,
    description,
    alternates: { canonical: data.url },
    openGraph: { title, description, url: data.url },
    robots: data.indexable ? undefined : { index: false, follow: true },
  };
}

export default async function Page({ params }: PageProps<"/ve/marca/[marca]">) {
  const data = await cargar((await params).marca);
  if (!data) notFound();
  if (esRedireccion(data)) permanentRedirect(data.redirect);
  const { marca: m, resumen: r, tasa } = data;

  const preguntas = [
    {
      pregunta: `¿Dónde comprar ${m.nombre} en Venezuela?`,
      respuesta: `${r.comercios} comercios venden ${m.nombre}.${data.comercios[0] ? ` El que más ofertas tiene es ${data.comercios[0].nombre} (${data.comercios[0].ofertas}).` : ""}`,
    },
    r.masBarato && {
      pregunta: `¿Cuál es el ${m.nombre} más barato?`,
      respuesta: `${r.masBarato.nombre}, desde ${usd(r.masBarato.usd)}${r.desdeBs ? ` (${bs(r.desdeBs)})` : ""}.`,
    },
    r.masBuscado && { pregunta: `¿Qué ${m.nombre} es el más buscado?`, respuesta: `${r.masBuscado.nombre}.` },
  ].filter((x): x is { pregunta: string; respuesta: string } => Boolean(x));

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-4 py-8">
      <Migas
        items={[
          { nombre: "Inicio", url: "/" },
          { nombre: "Marcas", url: "/ve/marcas" },
          { nombre: m.nombre, url: data.url },
        ]}
      />
      <AvisoDemo visible={data.datosDeEjemplo} />

      <div className="-mt-4 flex max-w-[760px] flex-col gap-4">
        <h1 className="text-[clamp(28px,5vw,36px)] leading-tight font-semibold">{data.titulo}</h1>
        {r.desde && (
          <PraisDice animo="tranqui">
            {m.nombre} tiene <b>{r.modelos} modelos</b> en {r.categorias} categorías y {r.comercios} comercios de Venezuela,
            desde <b>{usd(r.desde)}</b>
            {r.desdeBs ? ` (${bs(r.desdeBs)})` : ""}.{r.masBuscado && <> Lo más buscado: {r.masBuscado.nombre}.</>} Precios vistos el{" "}
            {fecha(r.actualizado)}.
          </PraisDice>
        )}
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl font-semibold">Categorías</h2>
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
          {data.categorias.map((c) => (
            <li key={c.url}>
              <Link
                href={c.url}
                className="flex min-h-11 flex-col gap-1 rounded-[12px] border border-linea bg-papel-alto p-5 hover:border-borde"
              >
                <span className="text-[17px] font-medium">{c.nombre}</span>
                <span className="text-sm text-tinta-suave">
                  {c.modelos} {c.modelos === 1 ? "modelo" : "modelos"}
                  {c.desde !== null ? ` · desde ${usd(c.desde)}` : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl font-semibold">Los {m.nombre} más buscados</h2>
        <Tarjetas items={data.top} />
        <NotaTasa tasa={tasa} actualizado={r.actualizado} />
      </section>

      <section className="flex max-w-[760px] flex-col gap-4">
        <h2 className="text-2xl font-semibold">Comercios que venden {m.nombre}</h2>
        <ul className="overflow-hidden rounded-[12px] border border-linea bg-papel-alto">
          {data.comercios.map((c) => (
            <li
              key={c.nombre}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-linea px-5 py-4 first:border-t-0"
            >
              <span className="font-medium">{c.nombre}</span>
              <span className="flex flex-wrap gap-4 text-sm text-tinta-suave">
                <span>
                  {c.ofertas} ofertas {m.nombre}
                </span>
                <span className={c.confianza < 50 ? "text-caro-texto" : ""}>{c.confianzaTexto}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <Preguntas items={preguntas} conJsonLd={data.indexable} />
    </main>
  );
}
