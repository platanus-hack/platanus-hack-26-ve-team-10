import type { Metadata } from "next";
import Link from "next/link";
import { getCategorias, getMarcas } from "@/lib/catalogo";
import { Migas } from "../ui";

// Índice A–Z de marcas (docs/marca.md) y de categorías: le da a Google un camino a todo el catálogo.
export const metadata: Metadata = {
  title: "Marcas y categorías en Venezuela",
  description: "Todas las marcas y categorías que compara usaprais en comercios de Venezuela, de la A a la Z.",
  alternates: { canonical: "/ve/marcas" },
};

export default async function Page() {
  // Si la API no responde al construir, la página sale vacía en vez de romper el build.
  const [marcas, categorias] = await Promise.all([getMarcas(), getCategorias()]);
  const letras = new Map<string, NonNullable<typeof marcas>>();
  for (const m of marcas ?? []) {
    const letra = m.nombre[0].toUpperCase();
    letras.set(letra, [...(letras.get(letra) ?? []), m]);
  }
  const grupos = new Map<string, NonNullable<typeof categorias>>();
  for (const c of categorias ?? []) grupos.set(c.grupo, [...(grupos.get(c.grupo) ?? []), c]);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8">
      <Migas
        items={[
          { nombre: "Inicio", url: "/" },
          { nombre: "Marcas", url: "/ve/marcas" },
        ]}
      />
      <div className="flex flex-col gap-2">
        <h1 className="text-[clamp(28px,5vw,36px)] leading-tight font-semibold">Marcas</h1>
        <p className="text-[17px] text-tinta-suave">
          {marcas?.length ?? 0} marcas con ofertas en comercios de Venezuela, de la A a la Z.
        </p>
      </div>

      <nav aria-label="Letras" className="flex flex-wrap gap-1">
        {[...letras.keys()].map((l) => (
          <a
            key={l}
            href={`#letra-${l}`}
            className="inline-flex size-11 items-center justify-center rounded-[12px] border border-linea font-medium hover:bg-papel-bajo"
          >
            {l}
          </a>
        ))}
      </nav>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-x-8 gap-y-6">
        {[...letras.entries()].map(([l, ms]) => (
          <section key={l} id={`letra-${l}`} className="flex flex-col gap-1">
            <h2 className="border-b border-linea pb-2 text-xl font-semibold">{l}</h2>
            <ul>
              {ms.map((m) => (
                <li key={m.slug}>
                  <Link href={m.url} className="flex min-h-11 items-center justify-between gap-3 hover:underline">
                    <span className="flex flex-col">
                      <span className="font-medium">{m.nombre}</span>
                      <span className="text-[13px] text-tinta-suave">{m.destino}</span>
                    </span>
                    <span className="text-[13px] text-tinta-suave tabular-nums">{m.modelos}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <section className="flex flex-col gap-4 border-t border-linea pt-8">
        <h2 className="text-2xl font-semibold">Categorías</h2>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-x-8 gap-y-6">
          {[...grupos.entries()].map(([grupo, cs]) => (
            <div key={grupo} className="flex flex-col gap-2">
              <h3 className="font-semibold">{grupo}</h3>
              <ul className="flex flex-col gap-1">
                {cs.map((c) => (
                  <li key={c.slug}>
                    <Link href={c.url} className="text-anil underline-offset-2 hover:underline">
                      {c.nombre}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
