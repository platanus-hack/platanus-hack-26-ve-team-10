"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { Icono } from "./icono";

type Message = { role: "user" | "prais"; text: string };

const EJEMPLOS = ["iPhone 15 de 128 GB", "Freidora de aire", "Harina PAN 1 kg en Caracas"];

export function Chat() {
  const sessionId = useRef<string | null>(null); // se crea con el primer mensaje, no en el prerender
  const lista = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    lista.current?.scrollTo({ top: lista.current.scrollHeight });
  }, [messages, loading]);

  async function preguntar(message: string) {
    if (!message || loading) return;

    sessionId.current ??= crypto.randomUUID();
    setMessages((current) => [...current, { role: "user", text: message }]);
    setInput("");
    setLoading(true);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: sessionId.current, message }),
      });
      const data = await response.json();
      setMessages((current) => [...current, { role: "prais", text: data.reply ?? "No pude responder." }]);
    } catch {
      setMessages((current) => [...current, { role: "prais", text: "Se cayó la conexión. Intenta de nuevo." }]);
    } finally {
      setLoading(false);
    }
  }

  function send(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    preguntar(input.trim());
  }

  return (
    <div id="buscar" className="flex w-full max-w-xl scroll-mt-24 flex-col gap-3">
      {messages.length > 0 && (
        <div
          ref={lista}
          aria-live="polite"
          className="flex max-h-[min(420px,55vh)] flex-col gap-3 overflow-y-auto rounded-[14px] border border-linea bg-papel-alto p-4"
        >
          {messages.map((message, index) =>
            message.role === "user" ? (
              <p
                key={index}
                className="mensaje max-w-[85%] self-end rounded-2xl rounded-br-md bg-accion px-4 py-2 whitespace-pre-wrap text-on-accion"
              >
                {message.text}
              </p>
            ) : (
              <div key={index} className="mensaje flex max-w-[92%] items-start gap-2 self-start">
                <Image src="/prais/prais-tranqui-circulo.svg" alt="" width={28} height={28} className="mt-1" />
                <p className="rounded-2xl rounded-tl-md bg-papel-bajo px-4 py-2 whitespace-pre-wrap">{message.text}</p>
              </div>
            ),
          )}
          {loading && (
            <div role="status" className="mensaje flex items-center gap-3 self-start">
              <Image src="/prais/prais-pensando-circulo.svg" alt="" width={28} height={28} />
              <div className="flex flex-col gap-1.5">
                <span className="text-sm text-tinta-suave">Revisando tiendas…</span>
                <span className="block h-1 w-28 overflow-hidden rounded-full bg-papel-bajo">
                  <span className="barra-carga block h-full w-2/5 rounded-full bg-sol" />
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <form
        onSubmit={send}
        className="flex flex-col gap-2 rounded-[14px] border-[2.5px] border-trazo bg-papel-alto p-2 shadow-[var(--sombra-sticker)] sm:flex-row"
      >
        <label className="flex min-h-12 min-w-0 flex-1 items-center gap-3 px-3">
          <Icono nombre="buscar" className="text-tinta-suave" />
          <span className="sr-only">Qué quieres comprar</span>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="¿Qué quieres comprar?"
            className="min-w-0 flex-1 bg-transparent text-[17px] outline-none placeholder:text-tinta-suave"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="presion inline-flex h-12 items-center justify-center gap-2 rounded-[10px] bg-accion px-5 font-medium text-on-accion hover:bg-accion-hover disabled:opacity-50"
        >
          Buscar precios
          <Icono nombre="flecha" size={18} />
        </button>
      </form>

      {messages.length === 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[15px]">
          <span className="text-tinta-suave">Prueba con</span>
          {EJEMPLOS.map((ejemplo) => (
            <button
              key={ejemplo}
              type="button"
              onClick={() => preguntar(ejemplo)}
              className="presion rounded-full border border-borde bg-papel-alto px-3 py-1.5 hover:bg-papel-bajo"
            >
              {ejemplo}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
