import React, { useState, useRef, useEffect } from "react";
import { Send, Bot, User, MessageSquare } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Badge } from "../ui/badge";

export interface ChatMessage {
  id: string;
  role: string;
  text: string;
  agentId?: string | null;
  seq?: number;
}

interface ChatPanelProps {
  messages: ChatMessage[];
  onSendMessage: (text: string) => void;
  isStreaming?: boolean;
  agentMode?: "mock" | "live";
}

export function ChatPanel({
  messages,
  onSendMessage,
  isStreaming = false,
  agentMode = "mock",
}: ChatPanelProps): JSX.Element {
  const [inputText, setInputText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isStreaming || agentMode === "mock") return;
    onSendMessage(inputText.trim());
    setInputText("");
  };

  const getAgentBadgeColor = (agentId?: string | null) => {
    if (!agentId) return "bg-blue-950 text-blue-300 border-blue-700/60";
    if (agentId.includes("triage")) return "bg-amber-950 text-amber-300 border-amber-700/60";
    if (agentId.includes("billing")) return "bg-emerald-950 text-emerald-300 border-emerald-700/60";
    if (agentId.includes("tech")) return "bg-purple-950 text-purple-300 border-purple-700/60";
    return "bg-slate-800 text-slate-300 border-slate-700";
  };

  return (
    <div className="flex h-full flex-col border-b border-border bg-card/60">
      {/* Panel Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 bg-slate-900/60">
        <div className="flex items-center gap-1.5">
          <MessageSquare className="h-4 w-4 text-primary" />
          <span className="text-xs font-semibold tracking-wide uppercase text-muted-foreground">
            Conversation
          </span>
        </div>
        <Badge variant="outline" className="text-[10px] font-mono">
          {messages.length} msgs
        </Badge>
      </div>

      {/* Messages List */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-xs text-muted-foreground p-4">
            <Bot className="h-8 w-8 mb-2 opacity-30 text-blue-400" />
            <p>No messages in session.</p>
            <p className="text-[11px] mt-1 text-slate-500">
              Select a scenario above or send a message to start conversation.
            </p>
          </div>
        ) : (
          messages.map((m) => {
            const isUser = m.role === "user";
            return (
              <div
                key={m.id}
                className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}
              >
                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  {isUser ? (
                    <>
                      <span>User</span>
                      <User className="h-3 w-3 text-slate-400" />
                    </>
                  ) : (
                    <>
                      <Bot className="h-3 w-3 text-blue-400" />
                      <Badge
                        variant="secondary"
                        className={`text-[9px] px-1 py-0 border ${getAgentBadgeColor(m.agentId)}`}
                      >
                        {m.agentId || "Agent"}
                      </Badge>
                    </>
                  )}
                </div>
                <div
                  className={`rounded-lg px-3 py-2 text-xs leading-relaxed max-w-[90%] shadow-sm ${
                    isUser
                      ? "bg-primary text-primary-foreground font-normal"
                      : "bg-slate-900/90 border border-slate-800 text-slate-200"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{m.text}</p>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Message Input Box */}
      <form onSubmit={handleSubmit} className="border-t border-border p-2 bg-slate-900/40 flex gap-2">
        <Input
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={
            agentMode === "mock"
              ? "Pick a scenario (mock mode)"
              : isStreaming
              ? "Agent responding..."
              : "Type a customer message..."
          }
          disabled={agentMode === "mock" || isStreaming}
          className="h-8 text-xs bg-slate-950/80 border-slate-800 focus-visible:ring-1"
        />
        <Button
          type="submit"
          size="sm"
          disabled={agentMode === "mock" || isStreaming || !inputText.trim()}
          className="h-8 px-2.5 text-xs"
        >
          <Send className="h-3.5 w-3.5" />
        </Button>
      </form>
    </div>
  );
}
