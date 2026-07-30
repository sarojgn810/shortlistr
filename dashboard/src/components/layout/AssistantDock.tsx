"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { MessageSquare, X, ArrowUp } from "lucide-react";
import { Button } from "@/src/components/ui/Button";
import { api, ApiError, type ChatTurn, type PendingConfirm } from "@/src/lib/api/client";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function AssistantDock() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending, open]);

  // Close on Escape when the dock is open.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const history = (): ChatTurn[] => messages.map((m) => ({ role: m.role, content: m.content }));

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    setPending(null);
    try {
      const res = await api.sendChat({ message: text, history: history() });
      setMessages((m) => [...m, { role: "assistant", content: res.reply || "(no reply)" }]);
      if (res.pending_confirm) setPending(res.pending_confirm);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (ok: boolean) => {
    if (!pending) return;
    const p = pending;
    setPending(null);
    if (!ok) {
      setMessages((m) => [...m, { role: "assistant", content: "Cancelled." }]);
      return;
    }
    setBusy(true);
    try {
      const res = await api.sendChat({ confirm_tool: p.tool, confirm_args: p.args });
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open assistant"
        className="fixed bottom-24 right-4 z-[60] flex h-12 w-12 items-center justify-center rounded-full bg-black text-lime shadow-xl transition-transform hover:scale-105 md:bottom-6"
      >
        <MessageSquare size={22} />
      </button>
    );
  }

  return (
    <div className="fixed right-0 top-0 z-[60] flex h-screen w-full flex-col border-l border-mist bg-white shadow-2xl sm:w-[380px]">
      <div className="flex items-center justify-between border-b border-mist px-4 py-3">
        <span className="flex items-center gap-2 font-bold text-ink">
          <MessageSquare size={18} /> Assistant
        </span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close assistant" className="text-stone hover:text-ink">
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-base text-stone">
            Ask about your search or run actions — &quot;what&apos;s in my inbox?&quot;, &quot;discover new
            jobs&quot;, &quot;what&apos;s working?&quot;. Anything that sends asks you to confirm first.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-left text-base ${
                m.role === "user" ? "bg-lime text-ink" : "bg-sage/40 text-ink"
              }`}
            >
              {m.content}
            </span>
          </div>
        ))}
        {pending && (
          <div className="rounded-2xl border border-mist bg-sage/30 p-3 text-base">
            <p className="font-bold text-ink">Confirm action</p>
            <p className="mt-1 text-stone">{pending.prompt}</p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="lime" isLoading={busy} onClick={() => confirm(true)}>
                Confirm
              </Button>
              <Button size="sm" variant="ghost" onClick={() => confirm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="flex gap-2 border-t border-mist p-3">
        <input
          className="flex-1 rounded-2xl border border-mist bg-white px-4 py-2.5 text-base text-ink outline-none focus:border-lime/40"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send(input);
          }}
          placeholder="Message shortlistr…"
          disabled={busy}
          aria-label="Message assistant"
        />
        <Button variant="lime" onClick={() => send(input)} isLoading={busy} disabled={!input.trim()} aria-label="Send">
          <ArrowUp size={18} />
        </Button>
      </div>
    </div>
  );
}
