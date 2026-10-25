import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getCategoria, getRutas, SIN_DATOS } from "@/lib/catalogo";
import { Listado, metadataDeListado } from "../../listado";

// [sub] es una marca (/ve/telefonos/xiaomi) o una faceta con demanda (/ve/televisores/32-pulgadas).
export async function generateStaticParams() {
  const { subcategorias } = await getRutas();
  return subcategorias.length
    ? subcategorias.map(([categoria, sub]) => ({ categoria, sub }))
    : [{ categoria: SIN_DATOS, sub: SIN_DATOS }];
}

async function cargar(categoria: string, sub: string) {
  return categoria === SIN_DATOS ? null : getCategoria(categoria, sub);
}

export async function generateMetadata({ params }: PageProps<"/ve/[categoria]/[sub]">): Promise<Metadata> {
  const { categoria, sub } = await params;
  const data = await cargar(categoria, sub);
  return data ? metadataDeListado(data) : {};
}

export default async function Page({ params }: PageProps<"/ve/[categoria]/[sub]">) {
  const { categoria, sub } = await params;
  const data = await cargar(categoria, sub);
  if (!data) notFound();
  return <Listado data={data} />;
}
