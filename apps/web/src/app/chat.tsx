"use client";

import { useRef, useState } from "react";

type Message = { role: "user" | "prais"; text: string };

export function Chat() {
  const sessionId = useRef<string | null>(null); // se crea con el primer mensaje, no en el prerender
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
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

  return (
    <div className="flex w-full max-w-xl flex-col gap-3 rounded-[12px] border border-linea bg-papel-alto p-3">
      <div className="flex flex-col gap-2 empty:hidden">
        {messages.map((message, index) => (
          <p
            key={index}
            className={`whitespace-pre-wrap rounded-2xl px-4 py-2 ${
              message.role === "user"
                ? "self-end bg-accion text-on-accion"
                : "self-start bg-papel-bajo"
            }`}
          >
            {message.text}
          </p>
        ))}
        {loading && <p className="self-start text-sm text-tinta-suave">Buscando precios…</p>}
      </div>
      <form onSubmit={send} className="flex gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="¿Qué quieres comprar? Ej: Harina PAN 1 kg en Caracas"
          aria-label="Qué quieres comprar"
          className="min-w-0 flex-1 rounded-[12px] border border-borde bg-papel-alto px-4 py-3"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-[12px] bg-accion px-5 py-3 font-medium text-on-accion hover:bg-accion-hover disabled:opacity-50"
        >
          Buscar
        </button>
      </form>
    </div>
  );
}
