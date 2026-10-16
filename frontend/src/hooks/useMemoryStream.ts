import { useState, useRef, useCallback } from "react";
import { getApiKey } from "../lib/api";

export interface UseMemoryStreamResult {
  isStreaming: boolean;
  error: string | null;
  startStream: (tenantId: string, sessionId: string, onEvent: (event: any) => void) => void;
  stopStream: () => void;
}

export function useMemoryStream(): UseMemoryStreamResult {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const stopStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const startStream = useCallback(
    async (tenantId: string, sessionId: string, onEvent: (event: any) => void) => {
      stopStream();

      const controller = new AbortController();
      abortControllerRef.current = controller;
      setIsStreaming(true);
      setError(null);

      try {
        const response = await fetch(`/t/${tenantId}/sessions/${sessionId}/stream`, {
          headers: {
            "Accept": "text/event-stream",
            "X-API-Key": getApiKey(tenantId),
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`SSE stream connection failed: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("Response body is not readable");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const block of lines) {
            const rawLines = block.split("\n");
            let eventData = "";

            for (const line of rawLines) {
              if (line.startsWith("data:")) {
                eventData += line.slice(5).trim();
              }
            }

            if (eventData) {
              try {
                const parsed = JSON.parse(eventData);
                onEvent(parsed);
              } catch (parseErr) {
                console.warn("Failed to parse SSE event data:", eventData);
              }
            }
          }
        }
      } catch (err: any) {
        if (err.name !== "AbortError") {
          setError(err.message || "Streaming error");
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [stopStream]
  );

  return {
    isStreaming,
    error,
    startStream,
    stopStream,
  };
}
