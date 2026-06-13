// Empty BASE = same-origin; Vite proxies /v1 to the compose api.
const BASE: string = import.meta.env.VITE_API_URL ?? "";
const WS_BASE = BASE
  ? BASE.replace(/^http/, "ws")
  : `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;

let token = localStorage.getItem("doppel_token") ?? "";

export async function ensureSession(): Promise<void> {
  if (token) return;
  const resp = await fetch(`${BASE}/v1/sessions`, { method: "POST" });
  const body = await resp.json();
  token = body.token;
  localStorage.setItem("doppel_token", token);
}

function authHeaders(): Record<string, string> {
  return { "X-Device-Token": token };
}

export interface AvatarUpload {
  avatarId: Promise<string>;
  finish: () => Promise<void>;
}

export function startAvatarUpload(stream: MediaStream): AvatarUpload {
  const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9")
    ? "video/webm;codecs=vp9"
    : "video/mp4";
  const ws = new WebSocket(`${WS_BASE}/v1/avatars/stream?t=${token}`);
  const recorder = new MediaRecorder(stream, { mimeType: mime });

  let resolveId!: (id: string) => void;
  let rejectId!: (e: Error) => void;
  const avatarId = new Promise<string>((res, rej) => { resolveId = res; rejectId = rej; });
  let resolveDone!: () => void;
  const done = new Promise<void>((r) => (resolveDone = r));

  ws.onopen = () => {
    ws.send(JSON.stringify({ mime }));
    recorder.start(1000); // chunks de 1s: upload durante a leitura
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.avatar_id && msg.status === undefined) resolveId(msg.avatar_id);
    if (msg.status === "processing") {
      ws.close();
      resolveDone();
    }
  };
  ws.onerror = () => rejectId(new Error("websocket error"));
  ws.onclose = (ev) => {
    if (!ev.wasClean) rejectId(new Error("websocket closed unexpectedly"));
  };
  recorder.ondataavailable = async (ev) => {
    if (ev.data.size > 0 && ws.readyState === WebSocket.OPEN) {
      ws.send(await ev.data.arrayBuffer());
    }
  };
  recorder.onstop = () => {
    // garante flush do ultimo chunk antes do done
    setTimeout(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ done: true }));
    }, 300);
  };

  return {
    avatarId,
    finish: () => {
      recorder.stop();
      return done;
    },
  };
}

export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export async function consumeSse(path: string, onEvent: SseHandler): Promise<void> {
  const resp = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let data = "{}";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        if (line.startsWith("data: ")) data = line.slice(6);
      }
      onEvent(event, JSON.parse(data));
    }
  }
}

export async function createVideo(avatarId: string, briefing: Blob): Promise<string> {
  const form = new FormData();
  form.append("avatar_id", avatarId);
  form.append("briefing", briefing, "briefing.webm");
  const resp = await fetch(`${BASE}/v1/videos`, {
    method: "POST", headers: authHeaders(), body: form,
  });
  return (await resp.json()).video_id;
}

export async function sendFeedback(
  videoId: string, rating: "up" | "down",
): Promise<{ video_id: string; action: string }> {
  const resp = await fetch(`${BASE}/v1/videos/${videoId}/feedback`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  });
  return resp.json();
}

export interface GalleryItem {
  video_id: string;
  created_at: string;
  fast_url: string;
}

export async function fetchGallery(): Promise<GalleryItem[]> {
  const resp = await fetch(`${BASE}/v1/gallery`, { headers: authHeaders() });
  return (await resp.json()).videos;
}

export async function deleteMe(): Promise<void> {
  await fetch(`${BASE}/v1/me`, { method: "DELETE", headers: authHeaders() });
  localStorage.removeItem("doppel_token");
  token = "";
}
