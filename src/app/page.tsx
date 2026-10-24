import { Chat } from "./chat";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center gap-8 px-4 py-16">
      <header className="flex max-w-xl flex-col gap-3 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">Prais</h1>
        <p className="text-lg opacity-80">
          El mismo producto puede costar muy distinto según dónde lo compres. Dinos qué buscas y comparamos los
          principales canales de venta de Venezuela para darte el mejor precio, con la tasa usada y qué tan
          confiable es cada comercio.
        </p>
      </header>
      <Chat />
    </main>
  );
}
