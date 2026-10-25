import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getCategoria, getRutas, SIN_DATOS } from "@/lib/catalogo";
import { Listado, metadataDeListado } from "../listado";

export async function generateStaticParams() {
  const { categorias } = await getRutas();
  return categorias.length ? categorias.map((categoria) => ({ categoria })) : [{ categoria: SIN_DATOS }];
}

async function cargar(categoria: string) {
  return categoria === SIN_DATOS ? null : getCategoria(categoria);
}

export async function generateMetadata({ params }: PageProps<"/ve/[categoria]">): Promise<Metadata> {
  const data = await cargar((await params).categoria);
  return data ? metadataDeListado(data) : {};
}

export default async function Page({ params }: PageProps<"/ve/[categoria]">) {
  const data = await cargar((await params).categoria);
  if (!data) notFound();
  return <Listado data={data} />;
}
