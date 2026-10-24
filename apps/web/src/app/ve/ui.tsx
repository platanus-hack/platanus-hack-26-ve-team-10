import Image from "next/image";
import Link from "next/link";
import type { Tarjeta, Tasa } from "@/lib/catalogo";
import { empresa } from "@/lib/empresa";
import { bs, fecha, usd } from "@/lib/formato";

// Piezas compartidas de las páginas del catálogo (/ve/...): capa de producto del design system,
// sobria. El amarillo `sol` solo marca la oferta más barata.

export function JsonLd({ data }: { data: object }) {
  return (
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />
  );
}

export function Migas({ items }: { items: { nombre: string; url: string }[] }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.nombre,
      item: `${empresa.sitio}${it.url}`,
    })),
  };
  return (
    <nav aria-label="Ruta" className="flex flex-wrap gap-1.5 text-sm text-tinta-suave">
      <JsonLd data={jsonLd} />
      {items.map((it, i) =>
        i === items.length - 1 ? (
          <span key={it.url} className="text-tinta">
            {it.nombre}
          </span>
        ) : (
          <span key={it.url} className="flex gap-1.5">
            <Link href={it.url} className="underline-offset-2 hover:underline">
              {it.nombre}
            </Link>
            <span aria-hidden="true">›</span>
          </span>
        ),
      )}
    </nav>
  );
}

// Mientras los precios vengan de la fuente de ejemplo, la página lo dice (y va noindex).
export function AvisoDemo({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <p role="note" className="rounded-[12px] border border-linea bg-papel-bajo px-4 py-3 text-[15px]">
      <strong>Datos de demostración.</strong> Los comercios y precios de esta página son de ejemplo mientras conectamos
      las fuentes reales. No los uses para comprar.
    </p>
  );
}

export function PraisDice({ animo, children }: { animo: "ganga" | "tranqui"; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <Image src={`/prais/prais-${animo}-circulo.svg`} alt="" width={36} height={36} className="mt-0.5 shrink-0" />
      <p className="text-lg leading-7">{children}</p>
    </div>
  );
}

export function Precio({
  valor,
  enBs,
  etiqueta,
  grande = false,
}: {
  valor: number;
  enBs: number | null;
  etiqueta?: string;
  grande?: boolean;
}) {
  return (
    <span className="flex flex-col tabular-nums">
      {etiqueta && <span className="text-[13px] text-tinta-suave">{etiqueta}</span>}
      <span className={grande ? "text-[32px] leading-9 font-semibold" : "text-xl leading-7 font-semibold"}>{usd(valor)}</span>
      {enBs !== null && <span className="text-sm text-tinta-suave">{bs(enBs)}</span>}
    </span>
  );
}

export function Tarjetas({ items }: { items: Tarjeta[] }) {
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
      {items.map((t) => (
        <li key={t.id}>
          <Link
            href={t.url}
            className="flex h-full flex-col gap-3 rounded-[12px] border border-linea bg-papel-alto p-4 hover:border-borde"
          >
            <span className="font-medium leading-snug">{t.nombre}</span>
            {t.usd !== null && (
              <Precio valor={t.usd} enBs={t.bs} etiqueta={t.condicion === "nuevo" ? "Desde" : `${t.condicion[0].toUpperCase()}${t.condicion.slice(1)} desde`} />
            )}
            <span className="mt-auto text-sm text-tinta-suave">
              En {t.comercios} {t.comercios === 1 ? "comercio" : "comercios"}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function Preguntas({ items, conJsonLd }: { items: { pregunta: string; respuesta: string }[]; conJsonLd: boolean }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((p) => ({ "@type": "Question", name: p.pregunta, acceptedAnswer: { "@type": "Answer", text: p.respuesta } })),
  };
  return (
    <section className="flex max-w-[760px] flex-col gap-3">
      {conJsonLd && <JsonLd data={jsonLd} />}
      <h2 className="text-2xl font-semibold">Preguntas frecuentes</h2>
      {items.map((p) => (
        <details key={p.pregunta} className="border-b border-linea py-3">
          <summary className="cursor-pointer text-[17px] font-medium">{p.pregunta}</summary>
          <p className="mt-2 text-tinta-suave">{p.respuesta}</p>
        </details>
      ))}
    </section>
  );
}

export function NotaTasa({ tasa, actualizado }: { tasa: Tasa; actualizado?: string | null }) {
  return (
    <p className="text-[13px] text-tinta-suave">
      Precios en dólares; bolívares a la {tasa.fuente} de {bs(tasa.usdToVes)} por dólar ({fecha(tasa.fecha)}).
      {actualizado ? ` Precios vistos el ${fecha(actualizado)}.` : ""} Confirma con el comercio antes de pagar.
    </p>
  );
}
