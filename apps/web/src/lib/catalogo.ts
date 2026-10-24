import { cacheLife } from "next/cache";

// Datos de las páginas del catálogo (/ve/...). La web no calcula nada: todo sale de la API
// (apps/api/app/lib/catalogo.py), que a su vez pide los precios a search_offers.
// Cada página trae `indexable` y `datosDeEjemplo`: con datos de ejemplo va noindex y con aviso.
const API = process.env.API_URL ?? "http://localhost:4000";

// Valor de relleno para generateStaticParams cuando la API no responde al construir
// (por ejemplo, `pnpm build` en local sin el backend corriendo). La página lo trata como 404.
export const SIN_DATOS = "__sin-datos__";

export type Tasa = { fuente: string; usdToVes: number; fecha: string };
export type Condicion = "nuevo" | "usado" | "reacondicionado";
export type Enlace = { nombre: string; url: string };

export type Oferta = {
  titulo: string;
  url: string;
  comercio: string;
  canal: string;
  zona: string;
  envia: boolean;
  confianza: number;
  confianzaTexto: string;
  condicion: Condicion;
  variante: string | null;
  usd: number | null;
  bs: number | null;
  precioPublicado: string | null;
  tasaUsada: string | null;
  visto: string;
  fuente: string;
  deEjemplo: boolean;
};

export type Tarjeta = {
  id: string;
  nombre: string;
  url: string;
  usd: number | null;
  bs: number | null;
  condicion: Condicion;
  comercios: number;
};

type Marcas = { slug: string; nombre: string; url: string };
type Categoria = { slug: string; nombre: string; singular: string; sinonimos: string[]; url: string };
type Estado = { tasa: Tasa; indexable: boolean; datosDeEjemplo: boolean };

export type PaginaProducto = Estado & {
  producto: { id: string; nombre: string; serie: string; url: string; marca: Marcas; categoria: Categoria; volumen: number };
  resumen: {
    nuevoDesde: number | null;
    nuevoDesdeBs: number | null;
    nuevoDesdeComercio: string | null;
    nuevoHasta: number | null;
    usadoDesde: number | null;
    reacondicionadoDesde: number | null;
    comercios: number;
    actualizado: string | null;
  };
  ofertas: Oferta[];
  variantes: { nombre: string; desde: number }[];
  alternativas: Tarjeta[];
};

export type Resumen = {
  modelos: number;
  comercios?: number;
  desde?: number | null;
  desdeBs?: number | null;
  masBuscado?: Enlace;
  masBarato?: (Enlace & { usd: number }) | null;
  actualizado?: string | null;
  categorias?: number;
};

export type PaginaCategoria = Estado & {
  tipo: "categoria" | "marca" | "faceta";
  titulo: string;
  url: string;
  categoria: Categoria;
  marca: Marcas | null;
  faceta: { slug: string; nombre: string } | null;
  resumen: Resumen;
  productos: Tarjeta[];
  marcas: (Marcas & { modelos: number })[];
  facetas: Enlace[];
  series: { nombre: string; modelos: number }[];
};

export type PaginaMarca = Estado & {
  marca: Marcas;
  titulo: string;
  url: string;
  resumen: Resumen;
  categorias: (Enlace & { modelos: number; desde: number | null })[];
  top: Tarjeta[];
  comercios: { nombre: string; canal: string; ofertas: number; confianza: number; confianzaTexto: string }[];
};

export type MarcaIndice = { slug: string; nombre: string; url: string; modelos: number; destino: string };
type Redireccion = { redirect: string };

// Next trata como fatal un error lanzado dentro de "use cache" al prerenderizar, aunque se capture
// afuera. Por eso, si la API no responde, se devuelve esta marca (cacheada solo por minutos) y cada
// página decide: las fichas fallan con 500 (no se cachea un 404 falso) y los índices salen vacíos.
type Fallo = { falloApi: true };

async function api<T>(ruta: string): Promise<T | null | Fallo> {
  "use cache";
  try {
    const res = await fetch(`${API}/catalogo${ruta}`);
    if (res.ok || res.status === 404) {
      cacheLife("hours");
      return res.ok ? res.json() : null;
    }
  } catch {}
  cacheLife("minutes");
  return { falloApi: true };
}

function esFallo(x: unknown): x is Fallo {
  return typeof x === "object" && x !== null && "falloApi" in x;
}

async function obligatorio<T>(ruta: string): Promise<T | null> {
  const x = await api<T>(ruta);
  if (esFallo(x)) throw new Error(`La API no respondió: /catalogo${ruta}`);
  return x;
}

async function opcional<T>(ruta: string): Promise<T | null> {
  const x = await api<T>(ruta);
  return esFallo(x) ? null : x;
}

export const getProducto = (slugId: string) => obligatorio<PaginaProducto | Redireccion>(`/producto/${encodeURIComponent(slugId)}`);
export const getCategoria = (cat: string, sub?: string) =>
  obligatorio<PaginaCategoria>(`/categoria/${encodeURIComponent(cat)}${sub ? `/${encodeURIComponent(sub)}` : ""}`);
export const getMarca = (slug: string) => obligatorio<PaginaMarca | Redireccion>(`/marca/${encodeURIComponent(slug)}`);
export const getMarcas = () => opcional<MarcaIndice[]>("/marcas");
export const getCategorias = () => opcional<(Categoria & { grupo: string })[]>("/categorias");
export const getSitemap = () => opcional<{ url: string; actualizado: string | null }[]>("/sitemap");

type Rutas = { productos: string[]; categorias: string[]; subcategorias: [string, string][]; marcas: string[] };

// Para generateStaticParams: si la API no responde al construir, devuelve [] y las páginas
// se generan al primer pedido.
export async function getRutas(): Promise<Rutas> {
  return (await opcional<Rutas>("/rutas")) ?? { productos: [], categorias: [], subcategorias: [], marcas: [] };
}

export function esRedireccion(x: object): x is Redireccion {
  return "redirect" in x;
}
