import type { Metadata } from "next";
import { empresa } from "@/lib/empresa";

export const metadata: Metadata = {
  title: "Política de privacidad",
  description: `Qué datos recoge usaprais (${empresa.razonSocial}), para qué los usa y cómo pedir que los borre.`,
  alternates: { canonical: "/privacidad" },
};

export default function Privacidad() {
  return (
    <main className="mx-auto flex w-full max-w-[68ch] flex-col gap-4 px-4 py-14 [&_h2]:mt-4 [&_h2]:text-lg [&_h2]:font-semibold [&_ul]:flex [&_ul]:list-disc [&_ul]:flex-col [&_ul]:gap-1.5 [&_ul]:pl-5">
      <h1 className="text-3xl font-semibold">Política de privacidad</h1>
      <p className="text-sm text-tinta-suave">Última actualización: {empresa.actualizado}</p>
      <p>
        Esta política explica qué datos recoge {empresa.razonSocial} (&quot;usaprais&quot;) cuando usas usaprais.com o le
        escribes a Prais por WhatsApp, para qué los usa y cómo puedes pedir que los borre.
      </p>

      <h2>Qué datos recogemos</h2>
      <ul>
        <li>Tu número de teléfono y nombre de perfil, cuando nos escribes por WhatsApp.</li>
        <li>El contenido de tus mensajes: los productos que buscas y la zona donde quieres comprar.</li>
        <li>Datos técnicos del sitio web, como el tipo de navegador y las páginas visitadas.</li>
      </ul>

      <h2>Para qué los usamos</h2>
      <ul>
        <li>Para buscar los precios que pediste y responderte.</li>
        <li>Para mejorar la búsqueda y detectar errores en el servicio.</li>
      </ul>
      <p>No vendemos tus datos ni los compartimos con tiendas o anunciantes. No te enviamos publicidad por WhatsApp.</p>

      <h2>Con quién los compartimos</h2>
      <p>
        Usamos proveedores que procesan datos por cuenta nuestra: Meta Platforms (WhatsApp Business), Kapso (conexión con la
        API de WhatsApp Business) y Google Cloud (alojamiento y modelos de IA). Cada uno trata los datos según sus propias
        políticas.
      </p>

      <h2>Cuánto tiempo los guardamos</h2>
      <p>Guardamos los mensajes hasta 90 días y luego los borramos o los dejamos anónimos.</p>

      <h2>Tus derechos</h2>
      <p>
        Puedes pedir una copia de tus datos, corregirlos o borrarlos escribiendo a {empresa.correo}. Respondemos en un
        máximo de 30 días. Para dejar de recibir mensajes por WhatsApp, escribe <strong>BAJA</strong>.
      </p>

      <h2>Contacto</h2>
      <p>
        {empresa.razonSocial} · {empresa.correo} · {empresa.telefono}
      </p>
    </main>
  );
}
