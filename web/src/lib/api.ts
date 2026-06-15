/**
 * Thin client for the doppel FastAPI backend (default http://localhost:8200).
 *
 * Auth is a per-device token (POST /v1/sessions) stored in localStorage and sent
 * as X-Device-Token. SSE uses fetch + a ReadableStream reader (EventSource cannot
 * set headers), mirroring the legacy frontend client.
 */
import type { PlanBrief, PlanRecord, PlanSummary, VideoPlan } from "./videoPlan";

const BASE: string = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8200";

let token = "";

function loadToken(): string {
  if (!token && typeof window !== "undefined") {
    token = localStorage.getItem("doppel_token") ?? "";
  }
  return token;
}

export async function ensureSession(): Promise<void> {
  if (loadToken()) return;
  const resp = await fetch(`${BASE}/v1/sessions`, { method: "POST" });
  if (!resp.ok) throw new Error(`session failed: ${resp.status}`);
  token = (await resp.json()).token;
  localStorage.setItem("doppel_token", token);
}

function authHeaders(): Record<string, string> {
  return { "X-Device-Token": loadToken() };
}

// --- Avatars (picker source) ---

export interface AvatarLook {
  label?: string | null;
  url: string;
}

export interface AvatarItem {
  avatar_id: string;
  status: string;
  label?: string | null;
  preview_url: string | null;
  voice_id: string | null;
  /** "video" (recorded) or "photo" (uploaded still). */
  kind?: string;
  looks?: AvatarLook[];
}

export interface AvatarDetail extends AvatarItem {
  hello_url?: string;
  feedback_url?: string;
  idle_url?: string;
}

export async function listAvatars(): Promise<AvatarItem[]> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/avatars`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`list avatars failed: ${resp.status}`);
  return (await resp.json()).avatars;
}

export async function getAvatar(avatarId: string): Promise<AvatarDetail> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/avatars/${avatarId}`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`get avatar failed: ${resp.status}`);
  return resp.json();
}

/**
 * Upload a recorded clip over the avatar WebSocket and return the new avatar id.
 * Protocol: send {mime,label} header → receive {avatar_id} → send bytes + {done}
 * → receive {status:"processing"} → server closes.
 */
export async function createAvatar(
  blob: Blob,
  mime: string,
  label?: string,
): Promise<string> {
  await ensureSession();
  const wsUrl = `${BASE.replace(/^http/, "ws")}/v1/avatars/stream?t=${encodeURIComponent(
    loadToken(),
  )}`;
  return new Promise<string>((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    let avatarId = "";
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      fn();
    };
    ws.onopen = () => ws.send(JSON.stringify({ mime, label: label ?? "" }));
    ws.onmessage = async (ev) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(ev.data as string);
      } catch {
        return;
      }
      if (msg.error) {
        ws.close();
        finish(() => reject(new Error(String(msg.error))));
        return;
      }
      if (msg.avatar_id && !avatarId) {
        avatarId = msg.avatar_id as string;
        ws.send(await blob.arrayBuffer());
        ws.send(JSON.stringify({ done: true }));
        return;
      }
      if (msg.status === "processing") finish(() => resolve(avatarId));
    };
    ws.onerror = () => finish(() => reject(new Error("avatar upload failed")));
    ws.onclose = (ev) => {
      // Sempre encerra a Promise. O servidor fecha sem "processing" quando o
      // upload excede o limite (code 1009) ou aborta; antes ficava pendente
      // eterno (UI presa em "Enviando...").
      finish(() =>
        reject(
          new Error(
            ev.code === 1009
              ? "O vídeo é muito grande. Grave um clipe mais curto e tente novamente."
              : "A conexão encerrou antes de concluir o envio. Tente novamente.",
          ),
        ),
      );
    };
  });
}

/**
 * Create an avatar from a single still image (any format, incl. webp). The photo
 * becomes the first frame; the server generates looks + an idle loop and skips
 * voice cloning (no audio). Returns the new avatar id.
 */
export async function createAvatarPhoto(file: Blob, label?: string): Promise<string> {
  await ensureSession();
  const form = new FormData();
  const name = (file as File).name || "photo";
  form.set("photo", file, name);
  if (label) form.set("label", label);
  const resp = await fetch(`${BASE}/v1/avatars/photo`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!resp.ok) throw new Error(`create avatar photo failed: ${resp.status}`);
  return (await resp.json()).avatar_id as string;
}

export async function renameAvatar(avatarId: string, label: string): Promise<void> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/avatars/${avatarId}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!resp.ok) throw new Error(`rename avatar failed: ${resp.status}`);
}

export async function deleteAvatar(avatarId: string): Promise<void> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/avatars/${avatarId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok && resp.status !== 204) throw new Error(`delete avatar failed: ${resp.status}`);
}

export function subscribeAvatar(avatarId: string, onEvent: SseHandler, signal?: AbortSignal) {
  return consumeSse(`/v1/avatars/${avatarId}/events`, onEvent, signal);
}

// --- Voices (reusable, manageable voice objects) ---

export interface VoiceCandidate {
  provider: string;
  label: string;
  model?: string;
  external_id?: string;
  preview_url?: string;
}

export interface VoiceSummary {
  voice_id: string;
  label: string;
  status: string;
  source: string;
  provider?: string | null;
  external_id?: string | null;
  avatar_id?: string | null;
  candidate_count: number;
  created_at: string;
}

export interface VoiceDetail {
  voice_id: string;
  label: string;
  status: string;
  source: string;
  provider?: string | null;
  external_id?: string | null;
  avatar_id?: string | null;
  candidates: VoiceCandidate[];
  created_at: string;
}

export interface CreateVoiceInput {
  label?: string;
  source: "footage" | "recorded" | "uploaded";
  avatarId?: string;
  sample?: Blob;
  sampleName?: string;
}

export async function listVoices(): Promise<VoiceSummary[]> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/voices`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`list voices failed: ${resp.status}`);
  return (await resp.json()).voices;
}

export async function getVoice(voiceId: string): Promise<VoiceDetail> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/voices/${voiceId}`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`get voice failed: ${resp.status}`);
  return resp.json();
}

export async function createVoice(
  input: CreateVoiceInput,
): Promise<{ voice_id: string; status?: string }> {
  await ensureSession();
  const form = new FormData();
  form.set("label", input.label ?? "Minha voz");
  form.set("source", input.source);
  if (input.avatarId) form.set("avatar_id", input.avatarId);
  if (input.sample) form.set("sample", input.sample, input.sampleName ?? "sample.webm");
  const resp = await fetch(`${BASE}/v1/voices`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!resp.ok) throw new Error(`create voice failed: ${resp.status}`);
  return await resp.json();
}

export async function selectVoice(
  voiceId: string,
  pick: { provider: string; model?: string; external_id?: string },
): Promise<VoiceDetail> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/voices/${voiceId}/select`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(pick),
  });
  if (!resp.ok) throw new Error(`select voice failed: ${resp.status}`);
  return resp.json();
}

/** A playable preview URL for any voice (synthesized + cached server-side on first call). */
export async function getVoicePreview(voiceId: string): Promise<string> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/voices/${voiceId}/preview`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`voice preview failed: ${resp.status}`);
  return (await resp.json()).preview_url as string;
}

export function subscribeVoice(voiceId: string, onEvent: SseHandler, signal?: AbortSignal) {
  return consumeSse(`/v1/voices/${voiceId}/events`, onEvent, signal);
}

// --- Plans (Video Agent artifact) ---

export interface CreatePlanInput extends PlanBrief {
  prompt: string;
}

export async function createPlan(input: CreatePlanInput): Promise<string> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/plans`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(`create plan failed: ${resp.status}`);
  return (await resp.json()).plan_id;
}

export async function getPlan(planId: string): Promise<PlanRecord> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/plans/${planId}`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`get plan failed: ${resp.status}`);
  return resp.json();
}

export async function listPlans(): Promise<PlanSummary[]> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/plans`, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`list plans failed: ${resp.status}`);
  return (await resp.json()).plans;
}

export async function patchPlan(planId: string, plan: VideoPlan): Promise<PlanRecord> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/plans/${planId}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
  if (!resp.ok) throw new Error(`patch plan failed: ${resp.status}`);
  return resp.json();
}

export interface GenerateOptions {
  avatar_id?: string;
  selections?: Record<string, unknown>;
  model_overrides?: Record<string, unknown>;
}

export async function generatePlan(
  planId: string,
  opts?: GenerateOptions,
): Promise<string> {
  await ensureSession();
  const resp = await fetch(`${BASE}/v1/plans/${planId}/generate`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(opts ?? {}),
  });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`generate failed: ${detail}`);
  }
  return (await resp.json()).video_id;
}

// --- Server-Sent Events ---

export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export async function consumeSse(
  path: string,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<void> {
  await ensureSession();
  const resp = await fetch(`${BASE}${path}`, { headers: authHeaders(), signal });
  if (!resp.ok || !resp.body) throw new Error(`sse failed: ${resp.status}`);
  const reader = resp.body.getReader();
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
      try {
        onEvent(event, JSON.parse(data));
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}

export function subscribePlan(planId: string, onEvent: SseHandler, signal?: AbortSignal) {
  return consumeSse(`/v1/plans/${planId}/events`, onEvent, signal);
}

export function subscribeVideo(videoId: string, onEvent: SseHandler, signal?: AbortSignal) {
  return consumeSse(`/v1/videos/${videoId}/events`, onEvent, signal);
}
