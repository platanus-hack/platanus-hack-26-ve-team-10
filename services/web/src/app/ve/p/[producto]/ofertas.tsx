"use client";

import { useState } from "react";
import type { Condicion, Oferta } from "@/lib/catalogo";
import { bs, CANALES, fecha, usd } from "@/lib/formato";

const PESTANAS: { id: Condicion; nombre: string }[] = [
  { id: "nuevo", nombre: "Nuevo" },
  { id: "usado", nombre: "Usado" },
  { id: "reacondicionado", nombre: "Reacondicionado" },
];

// Tabla de ofertas de la ficha: pestañas por condición y filtro de ciudad. Solo filtra lo que
// ya mandó la API (ordenado por precio); no calcula precios.
export function Ofertas({ ofertas }: { ofertas: Oferta[] }) {
  const pestanas = PESTANAS.filter((p) => ofertas.some((o) => o.condicion === p.id));
  const [condicion, setCondicion] = useState<Condicion>(pestanas[0]?.id ?? "nuevo");
  const [ciudad, setCiudad] = useState("");
  const ciudades = [...new Set(ofertas.map((o) => o.zona))].sort();
  const visibles = ofertas.filter((o) => o.condicion === condicion && (!ciudad || o.zona === ciudad || o.envia));
  const masBarata = visibles.find((o) => o.usd !== null);

  return (
    <section aria-labelledby="ofertas-h" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="ofertas-h" className="text-2xl font-semibold">
          Dónde comprarlo
        </h2>
        <label className="flex flex-col gap-1 text-[13px] text-tinta-suave">
          Ciudad
          <select
            value={ciudad}
            onChange={(e) => setCiudad(e.target.value)}
            className="h-11 min-w-40 rounded-[12px] border border-borde bg-papel-alto px-3 text-[15px] text-tinta"
          >
            <option value="">Todas</option>
            {ciudades.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div role="tablist" aria-label="Condición" className="flex gap-1 border-b border-linea">
        {pestanas.map((p) => {
          const activa = p.id === condicion;
          return (
            <button
              key={p.id}
              role="tab"
              aria-selected={activa}
              onClick={() => setCondicion(p.id)}
              className={`-mb-px min-h-11 border-b-2 px-4 text-[15px] ${activa ? "border-tinta font-semibold" : "border-transparent text-tinta-suave"}`}
            >
              {p.nombre} ({ofertas.filter((o) => o.condicion === p.id).length})
            </button>
          );
        })}
      </div>

      {visibles.length === 0 ? (
        <p className="text-tinta-suave">No hay ofertas en {ciudad} con esa condición. Prueba con otra ciudad.</p>
      ) : (
        <ol className="overflow-hidden rounded-[12px] border border-linea bg-papel-alto">
          {visibles.map((o, i) => {
            const destacada = o === masBarata && condicion === "nuevo";
            return (
              <li
                key={`${o.comercio}-${o.url}`}
                className={`flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-linea px-5 py-4 first:border-t-0 ${destacada ? "bg-sol-tinte" : ""}`}
              >
                <span className="w-6 font-semibold text-tinta-suave tabular-nums">{i + 1}</span>
                <div className="flex min-w-0 flex-[999_1_320px] flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[17px] font-medium">{o.comercio}</span>
                    <span className="rounded-[6px] bg-papel-bajo px-2 py-0.5 text-[13px]">{CANALES[o.canal] ?? o.canal}</span>
                    {destacada && <span className="rounded-[6px] bg-sol px-2 py-0.5 text-[13px] text-on-sol">Más barato</span>}
                  </div>
                  <span className="text-sm text-tinta-suave">
                    {[o.variante, o.condicion[0].toUpperCase() + o.condicion.slice(1)].filter(Boolean).join(" · ")} ·{" "}
                    {o.envia ? `${o.zona}, envío nacional` : `${o.zona}, retiro en persona`}
                  </span>
                  <span className={`text-sm ${o.confianza < 50 ? "text-caro-texto" : "text-tinta-suave"}`}>{o.confianzaTexto}</span>
                  <span className="text-[13px] text-tinta-suave">
                    Visto el {fecha(o.visto)}
                    {o.tasaUsada ? ` · publicado en ${o.precioPublicado}, convertido a ${o.tasaUsada}` : ""}
                  </span>
                </div>
                <div className="flex flex-[1_1_200px] items-center justify-end gap-4">
                  {o.usd !== null ? (
                    <span className="flex flex-col text-right tabular-nums">
                      <span className="text-xl font-semibold">{usd(o.usd)}</span>
                      {o.bs !== null && <span className="text-sm text-tinta-suave">{bs(o.bs)}</span>}
                    </span>
                  ) : (
                    <span className="text-[15px] text-tinta-suave">Precio al DM</span>
                  )}
                  <a
                    href={o.url}
                    rel="nofollow noopener"
                    target="_blank"
                    className="inline-flex min-h-11 items-center rounded-[12px] border border-borde bg-papel-alto px-4 text-[15px] font-medium whitespace-nowrap hover:bg-papel-bajo"
                  >
                    {o.usd !== null ? "Ir al comercio" : "Consultar"}
                  </a>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
