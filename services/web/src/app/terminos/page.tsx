import type { Metadata } from "next";
import { empresa } from "@/lib/empresa";

export const metadata: Metadata = {
  title: "Términos de uso",
  description: `Condiciones para usar usaprais, el comparador de precios de ${empresa.razonSocial}.`,
  alternates: { canonical: "/terminos" },
};

export default function Terminos() {
  return (
    <main className="mx-auto flex w-full max-w-[68ch] flex-col gap-4 px-4 py-14">
      <h1 className="text-3xl font-semibold">Términos de uso</h1>
      <p className="text-sm text-tinta-suave">Última actualización: {empresa.actualizado}</p>
      <ul className="flex list-disc flex-col gap-2 pl-5">
        <li>usaprais es gratis para quien compra. No vende productos ni cobra comisión a las tiendas.</li>
        <li>
          Los precios vienen de publicaciones públicas y pueden cambiar. Cada precio indica su fuente y la fecha en que se
          revisó. Confirma el precio con la tienda antes de pagar.
        </li>
        <li>La conversión a bolívares usa la tasa que se muestra junto al precio.</li>
        <li>La compra es entre tú y la tienda. usaprais no responde por la entrega, la garantía ni el estado del producto.</li>
        <li>No uses el servicio para enviar contenido ilegal, spam o mensajes automatizados.</li>
        <li>
          El servicio lo presta {empresa.razonSocial}, una empresa registrada en Estados Unidos. Estos términos se rigen
          por las leyes de Estados Unidos.
        </li>
        <li>Para cualquier duda sobre estos términos, escribe a {empresa.correo}.</li>
      </ul>
    </main>
  );
}
