import { useEffect, useRef } from "react";

export function useWebSocket(url: string | null, onMessage: (data: unknown) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!url) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        onMessageRef.current(JSON.parse(ev.data));
      } catch {
        onMessageRef.current(ev.data);
      }
    };

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30000);

    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, [url]);

  return wsRef;
}
