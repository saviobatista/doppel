/**
 * Video Agent artifact types — mirror of the backend plan schema
 * (backend/src/doppel_api/providers/plan.py). The plan is the editable object
 * the user reviews before submitting it for generation.
 */

export interface Source {
  title: string;
  url: string;
}

export interface Research {
  summary: string;
  angle: string;
  key_points: string[];
  sources?: Source[];
}

export interface Direction {
  shot: string;
  framing?: string;
  camera?: string;
  mood: string;
  b_roll_prompt?: string;
}

export interface Transition {
  type: string;
  duration_seconds?: number;
}

export type SceneKind = "avatar" | "broll";

export interface Scene {
  id: string;
  title: string;
  kind: SceneKind;
  narration?: string;
  on_screen_text?: string;
  duration_seconds: number;
  direction: Direction;
  transition_out?: Transition;
  overlays?: string[];
}

export interface MusicTrack {
  title: string;
  mood: string;
  bpm?: number;
}

export interface Sfx {
  cue: string;
  at_scene?: string;
}

export interface AudioDesign {
  music: MusicTrack;
  sfx?: Sfx[];
  voiceover?: { voice_label?: string; tone?: string };
  ducking?: boolean;
}

export interface MediaAsset {
  label: string;
  kind: "image" | "video";
  prompt?: string;
  search_query?: string;
  scene_id?: string;
  /** Presigned URL of the generated/scraped preview still (after materialization). */
  preview_url?: string;
  /** For kind === "video": a direct mp4 URL, or a YouTube watch link when deferred. */
  video_url?: string;
  /** "scraped" | "generated" | "youtube". */
  source?: string;
  /** Link to the page/video the asset came from. */
  source_link?: string;
  key?: string;
  /** YouTube footage metadata (links fetched at build, download deferred). */
  channel?: string;
  published?: string;
  views?: string;
  length?: string;
  deferred?: boolean;
}

export interface AudioTrack {
  label: string;
  /** "fal" | "elevenlabs" | "scraped". */
  source: string;
  kind: string;
  preview_url?: string;
  source_link?: string;
  key?: string;
}

export interface DesignElement {
  id: string;
  label: string;
  kind: string;
  /** Presigned URL of the rendered overlay PNG (set after materialization). */
  preview_url?: string;
}

export interface ResourceRef {
  id: string;
  label: string;
}

export interface Resources {
  avatars?: ResourceRef[];
  voices?: ResourceRef[];
  media?: MediaAsset[];
  /** Real, recent YouTube videos for the topic (links + thumbnails; download deferred). */
  footage?: MediaAsset[];
  design_elements?: DesignElement[];
  audio?: AudioTrack[];
}

export interface PlanMeta {
  duration_seconds?: number;
  orientation?: string;
  language?: string;
  credits_estimate?: string;
}

export interface VideoPlan {
  title: string;
  logline?: string;
  style: string;
  research: Research;
  script: { scenes: Scene[] };
  audio: AudioDesign;
  resources: Resources;
  meta?: PlanMeta;
}

export type PlanStatus =
  | "researching"
  | "scripting"
  | "directing"
  | "ready"
  | "generating"
  | "generated"
  | "failed";

export interface PlanBrief {
  prompt: string;
  avatar_id?: string | null;
  voice_id?: string | null;
  avatar_label?: string | null;
  voice_label?: string | null;
  duration_seconds?: number;
  orientation?: string;
  language?: string;
}

export interface BundleAsset {
  kind: "media" | "overlay" | "audio" | "footage_thumb";
  key: string;
  label?: string;
  content_type?: string;
  download_url?: string;
}

export interface Bundle {
  plan_id: string;
  title?: string;
  plan_key?: string;
  plan_download_url?: string;
  counts?: Record<string, number>;
  assets?: BundleAsset[];
  language?: string;
}

export interface PlanRecord {
  plan_id: string;
  status: PlanStatus;
  brief: PlanBrief;
  plan: VideoPlan | null;
  bundle: Bundle | null;
  video_id: string | null;
  created_at: string;
}

/** Lightweight projects-grid row from GET /v1/plans. */
export interface PlanSummary {
  plan_id: string;
  status: PlanStatus;
  title: string;
  prompt?: string;
  video_id: string | null;
  created_at: string;
  counts?: Record<string, number>;
  cover_url?: string | null;
}
