import type { Metadata } from "next";
import Link from "next/link";
import { empresa } from "@/lib/empresa";
import { guia, guias } from "@/lib/guias";

export function metadataDeGuia(slug: string): Metadata {
  const { title, description } = guia(slug);
  return { title, description, alternates: { canonical: `/${slug}` }, openGraph: { title, description } };
}

// Página estática de SEO/GEO: respuesta primero, detalle después, preguntas frecuentes al final.
export function PaginaGuia({ slug }: { slug: string }) {
  const { h1, resumen, secciones, preguntas } = guia(slug);
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: preguntas.map((p) => ({
        "@type": "Question",
        name: p.pregunta,
        acceptedAnswer: { "@type": "Answer", text: p.respuesta },
      })),
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Inicio", item: empresa.sitio },
        { "@type": "ListItem", position: 2, name: h1, item: `${empresa.sitio}/${slug}` },
      ],
    },
  ];

  return (
    <main className="mx-auto flex w-full max-w-[68ch] flex-col gap-5 px-4 py-14">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />
      <nav aria-label="Ruta" className="text-sm text-tinta-suave">
        <Link href="/" className="underline underline-offset-2">
          Inicio
        </Link>{" "}
        › {h1}
      </nav>
      <h1 className="text-[clamp(28px,5vw,40px)] leading-tight font-semibold">{h1}</h1>
      <p className="text-lg">{resumen}</p>
      <Link href="/" className="btn-cartel self-start">
        Compara un precio ahora
      </Link>

      {secciones.map((seccion) => (
        <section key={seccion.titulo} className="mt-4 flex flex-col gap-3">
          <h2 className="text-2xl font-semibold">{seccion.titulo}</h2>
          {seccion.parrafos.map((parrafo) => (
            <p key={parrafo}>{parrafo}</p>
          ))}
        </section>
      ))}

      <section className="mt-4 flex flex-col gap-3">
        <h2 className="text-2xl font-semibold">Preguntas frecuentes</h2>
        <dl className="overflow-hidden rounded-[12px] border border-linea bg-papel-alto">
          {preguntas.map((p) => (
            <div key={p.pregunta} className="flex flex-col gap-1 border-b border-linea px-4 py-4 last:border-0">
              <dt className="font-semibold">{p.pregunta}</dt>
              <dd>{p.respuesta}</dd>
            </div>
          ))}
        </dl>
      </section>

      <nav aria-label="Más guías" className="mt-6 flex flex-col gap-2 border-t border-linea pt-6">
        <strong>También te puede servir</strong>
        {guias
          .filter((g) => g.slug !== slug)
          .map((g) => (
            <Link key={g.slug} href={`/${g.slug}`} className="text-anil underline underline-offset-2">
              {g.h1}
            </Link>
          ))}
      </nav>
    </main>
  );
}
