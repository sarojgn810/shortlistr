"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import DashboardShell from "@/src/components/layout/DashboardShell";
import { Button } from "@/src/components/ui/Button";
import { GroqKeyModal } from "@/src/components/ai/GroqKeyModal";
import { useSetupStatus } from "@/src/hooks/useSetupStatus";
import { api, ApiError, type ChatTurn, type PendingConfirm } from "@/src/lib/api/client";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [showGroq, setShowGroq] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const { status: setupStatus, refetch: refetchSetup } = useSetupStatus();
  const llmAvailable = setupStatus?.llm?.available ?? false;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

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
      if (res.needs_llm && !llmAvailable) setShowGroq(true);
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

  return (
    <DashboardShell title="Chat" breadcrumbs={["Home", "Chat"]}>
      <div className="mb-4 w-full rounded-2xl border border-mist/60 bg-mist/40 px-5 py-4 text-base text-stone">
        This page is no longer in the menu — use the{" "}
        <strong className="text-ink">assistant dock</strong> (message icon, bottom-right corner) instead.
      </div>

      {!llmAvailable && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-mist bg-sage/30 px-5 py-4">
          <div>
            <p className="font-bold text-ink">AI not connected</p>
            <p className="mt-1 text-sm text-stone">
              Chat works with basic commands only until you add a free Groq key or Local AI.
            </p>
          </div>
          <Button variant="lime" size="sm" onClick={() => setShowGroq(true)}>
            <Sparkles size={14} /> Connect Groq
          </Button>
        </div>
      )}

      <div className="flex h-[calc(100vh-220px)] w-full flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto rounded-[28px] border border-mist bg-white p-6">
          {messages.length === 0 && (
            <p className="text-base text-stone">
              Ask me anything — &quot;what&apos;s in my inbox?&quot;, &quot;discover new jobs&quot;,
              &quot;what&apos;s working?&quot;. I can run actions too; anything that sends asks you to confirm
              first.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <span
                className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-left text-base ${
                  m.role === "user" ? "bg-lime text-ink" : "bg-sage/40 text-ink"
                }`}
              >
                {m.content}
              </span>
            </div>
          ))}
          {pending && (
            <div className="rounded-2xl border border-mist bg-sage/30 p-4 text-base">
              <p className="font-bold text-ink">Confirm action</p>
              <p className="mt-1 text-stone">{pending.prompt}</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="lime" onClick={() => confirm(true)} isLoading={busy}>
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
        <div className="mt-4 flex gap-2">
          <input
            className="flex-1 rounded-2xl border border-mist bg-white px-4 py-3 text-base text-ink outline-none focus:border-lime/40"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send(input);
            }}
            placeholder="Message shortlistr…"
            disabled={busy}
          />
          <Button variant="lime" onClick={() => send(input)} isLoading={busy} disabled={!input.trim()}>
            Send
          </Button>
        </div>
      </div>
      <GroqKeyModal
        open={showGroq}
        onClose={() => setShowGroq(false)}
        onSaved={() => void refetchSetup()}
      />
    </DashboardShell>
  );
}
