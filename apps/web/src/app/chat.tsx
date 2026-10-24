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
    <div className="flex w-full max-w-xl flex-col gap-3">
      <div className="flex flex-col gap-2">
        {messages.map((message, index) => (
          <p
            key={index}
            className={`whitespace-pre-wrap rounded-2xl px-4 py-2 ${
              message.role === "user"
                ? "self-end bg-foreground text-background"
                : "self-start bg-black/5 dark:bg-white/10"
            }`}
          >
            {message.text}
          </p>
        ))}
        {loading && <p className="self-start text-sm opacity-60">Buscando precios…</p>}
      </div>
      <form onSubmit={send} className="flex gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="¿Qué quieres comprar? Ej: Harina PAN 1 kg en Caracas"
          className="flex-1 rounded-full border border-black/15 bg-transparent px-4 py-2 dark:border-white/20"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-full bg-foreground px-5 py-2 text-background disabled:opacity-50"
        >
          Buscar
        </button>
      </form>
    </div>
  );
}
