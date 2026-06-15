"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  X,
  Video,
  Smartphone,
  Monitor,
  Camera,
  Mic,
  Upload,
  ImagePlus,
  Languages,
  Loader2,
  CameraOff,
  CheckCircle2,
} from "lucide-react";
import { Dropdown, type DropdownOption } from "@/components/ui/Dropdown";
import { AudioMeter } from "@/components/ui/AudioMeter";
import { RecordingTips } from "@/components/avatar/RecordingTips";
import { AvatarRecorder } from "@/components/avatar/AvatarRecorder";
import { RecordReview } from "@/components/avatar/RecordReview";
import { createAvatar, createAvatarPhoto } from "@/lib/api";
import { cn } from "@/lib/cn";

type Tab = "webcam" | "phone" | "photo";
type Aspect = "landscape" | "portrait";
type Status = "loading" | "ready" | "denied" | "error";
type Step = "config" | "tips" | "recording" | "review";

const ASPECTS: DropdownOption[] = [
  { value: "portrait", label: "Retrato" },
  { value: "landscape", label: "Paisagem" },
];

const LANGS: DropdownOption[] = [
  { value: "pt-BR", label: "Português" },
  { value: "en-US", label: "Inglês" },
  { value: "es-MX", label: "Espanhol" },
];

export function CloneAvatarSetup() {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [tab, setTab] = useState<Tab>("webcam");
  const [aspect, setAspect] = useState<Aspect>("landscape");
  const [cameras, setCameras] = useState<DropdownOption[]>([]);
  const [mics, setMics] = useState<DropdownOption[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [micId, setMicId] = useState("");
  const [lang, setLang] = useState("pt-BR");
  const [status, setStatus] = useState<Status>("loading");
  const [errMsg, setErrMsg] = useState("");
  const [activeStream, setActiveStream] = useState<MediaStream | null>(null);
  const [step, setStep] = useState<Step>("config");
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const recordedBlobRef = useRef<Blob | null>(null);

  // Photo-upload flow (a still becomes the avatar's first frame).
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoName, setPhotoName] = useState("");
  const [creatingPhoto, setCreatingPhoto] = useState(false);
  const [photoErr, setPhotoErr] = useState<string | null>(null);

  // Mirror the latest selection so the async acquire helper never reads stale
  // values when invoked from effects/listeners.
  const selRef = useRef<{ cameraId: string; micId: string; aspect: Aspect }>({
    cameraId: "",
    micId: "",
    aspect: "landscape",
  });
  useEffect(() => {
    selRef.current = { cameraId, micId, aspect };
  }, [cameraId, micId, aspect]);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  /** List devices regardless of permission state (labels appear once granted). */
  const refreshDevices = useCallback(async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const toOpt = (d: MediaDeviceInfo, i: number, fb: string): DropdownOption => ({
        value: d.deviceId,
        label: d.label || `${fb} ${i + 1}`,
      });
      setCameras(
        devices.filter((d) => d.kind === "videoinput").map((d, i) => toOpt(d, i, "Câmera")),
      );
      setMics(
        devices.filter((d) => d.kind === "audioinput").map((d, i) => toOpt(d, i, "Microfone")),
      );
    } catch {
      /* ignore */
    }
  }, []);

  const startStream = useCallback(
    async (opts?: { camId?: string; micId?: string; aspect?: Aspect }) => {
      const camId = opts?.camId ?? selRef.current.cameraId;
      const mId = opts?.micId ?? selRef.current.micId;

      setStatus("loading");
      stopStream();

      // Webcams are landscape sensors: asking for a tall 1080x1920 portrait makes
      // the browser hand back a small cropped feed that looks soft when shown
      // fullscreen. Always request the sensor's full 1080p frame and crop to the
      // chosen aspect with object-cover instead — the capture stays sharp.
      const resolution: MediaTrackConstraints = {
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      };
      const audio: MediaStreamConstraints["audio"] = mId ? { deviceId: { exact: mId } } : true;
      const acquire = (useExactCam: boolean) =>
        navigator.mediaDevices.getUserMedia({
          video: {
            ...(useExactCam && camId ? { deviceId: { exact: camId } } : {}),
            ...resolution,
            frameRate: { ideal: 30 },
          },
          audio,
        });

      try {
        let stream: MediaStream;
        try {
          stream = await acquire(true);
        } catch (inner) {
          // A specific camera that's gone/incompatible: retry with defaults once.
          const ie = inner as DOMException;
          if ((ie?.name === "OverconstrainedError" || ie?.name === "NotFoundError") && camId) {
            stream = await acquire(false);
          } else {
            throw inner;
          }
        }
        streamRef.current = stream;
        setActiveStream(stream);
        if (videoRef.current) videoRef.current.srcObject = stream;

        await refreshDevices();
        const vs = stream.getVideoTracks()[0]?.getSettings();
        setCameraId(vs?.deviceId || "");
        setMicId(stream.getAudioTracks()[0]?.getSettings().deviceId || "");
        setStatus("ready");
      } catch (e) {
        const err = e as DOMException;
        // Populate the device lists even on failure so the user can pick another.
        await refreshDevices();
        setActiveStream(null);

        if (err?.name === "NotAllowedError" || err?.name === "SecurityError") {
          setStatus("denied");
        } else if (err?.name === "NotReadableError" || err?.name === "AbortError") {
          setErrMsg(
            "A câmera está em uso por outro aplicativo (ex.: outra aba, Zoom, Meet). Feche-o e tente novamente.",
          );
          setStatus("error");
        } else if (err?.name === "NotFoundError") {
          setErrMsg("Nenhuma câmera encontrada. Conecte uma câmera e tente novamente.");
          setStatus("error");
        } else {
          setErrMsg(err?.message || "Não foi possível iniciar a câmera.");
          setStatus("error");
        }
      }
    },
    [stopStream, refreshDevices],
  );

  // List devices up front (and react to hot-plugging) so the dropdowns are never
  // empty, even before/without camera permission.
  useEffect(() => {
    const id = setTimeout(() => refreshDevices(), 0);
    const md = navigator.mediaDevices;
    const onChange = () => refreshDevices();
    md?.addEventListener?.("devicechange", onChange);
    return () => {
      clearTimeout(id);
      md?.removeEventListener?.("devicechange", onChange);
    };
  }, [refreshDevices]);

  // Acquire on mount / when returning to the webcam tab. Deferred to a macrotask
  // so the camera API (an external system) isn't driven synchronously from the
  // effect body.
  useEffect(() => {
    if (tab !== "webcam") return;
    const id = setTimeout(() => startStream(), 0);
    return () => {
      clearTimeout(id);
      stopStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Reattach the still-live stream to the preview when returning to config
  // (the preview <video> unmounts during the recording/review steps).
  useEffect(() => {
    if (step === "config" && videoRef.current && activeStream) {
      videoRef.current.srcObject = activeStream;
    }
  }, [step, activeStream]);

  // Release any recorded object URL on unmount.
  useEffect(() => {
    return () => {
      if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    };
  }, [recordedUrl]);

  const handleCamera = (id: string) => {
    setCameraId(id);
    startStream({ camId: id });
  };
  const handleMic = (id: string) => {
    setMicId(id);
    startStream({ micId: id });
  };
  const handleAspect = (v: Aspect) => {
    setAspect(v);
    if (tab === "webcam") startStream({ aspect: v });
  };

  const close = () => {
    stopStream();
    router.push("/avatar");
  };

  const handleFinish = (blob: Blob) => {
    recordedBlobRef.current = blob;
    setRecordedUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(blob);
    });
    setStep("review");
  };

  // Upload the recording over the WebSocket, then hand off to the avatar's
  // ready/voice screen which streams prep progress and runs voice setup.
  const handleCreate = async (name: string) => {
    const blob = recordedBlobRef.current;
    if (!blob) return;
    const id = await createAvatar(blob, blob.type || "video/webm", name);
    stopStream();
    router.push(`/avatar/${id}?new=1`);
  };

  const onPhotoPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPhotoErr(null);
    setPhotoFile(f);
    setPhotoUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(f);
    });
    setPhotoName((n) => n || f.name.replace(/\.[^.]+$/, ""));
  };

  const createFromPhoto = async () => {
    if (!photoFile || creatingPhoto) return;
    setCreatingPhoto(true);
    setPhotoErr(null);
    try {
      const id = await createAvatarPhoto(photoFile, photoName.trim());
      stopStream();
      router.push(`/avatar/${id}?new=1`);
    } catch (e) {
      setPhotoErr((e as Error).message);
      setCreatingPhoto(false);
    }
  };

  // Release the photo preview URL on unmount.
  useEffect(() => {
    return () => {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    };
  }, [photoUrl]);

  const ready = status === "ready";
  const isPortrait = aspect === "portrait";

  const config = (
    <div className="flex min-w-0 flex-1 flex-col">
      {/* Minimal header: just a close button */}
      <header className="flex h-14 shrink-0 items-center justify-end px-6">
        <button
          onClick={close}
          aria-label="Fechar"
          className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
        >
          <X className="h-5 w-5" />
        </button>
      </header>

      <main className="flex-1 overflow-y-auto px-6 pb-12">
        <div className="mx-auto w-full max-w-2xl">
          {/* Title */}
          <div className="text-center">
            <h1 className="text-2xl font-bold text-white">Crie seu Avatar em 15 segundos</h1>
            <p className="mt-2 text-sm text-zinc-400">
              Grave seu movimento uma vez e reutilize-o em qualquer visual deste avatar.{" "}
              <button className="inline-flex items-center gap-1 font-medium text-accent hover:underline">
                <Upload className="h-3.5 w-3.5" />
                Carregar material
              </button>
            </p>
          </div>

          {/* Source tabs */}
          <div className="mx-auto mt-6 grid max-w-lg grid-cols-3 rounded-full border border-white/10 bg-white/5 p-1">
            <TabButton active={tab === "webcam"} onClick={() => setTab("webcam")} icon={Video}>
              Webcam
            </TabButton>
            <TabButton active={tab === "phone"} onClick={() => setTab("phone")} icon={Smartphone}>
              Celular
            </TabButton>
            <TabButton active={tab === "photo"} onClick={() => setTab("photo")} icon={ImagePlus}>
              Carregar foto
            </TabButton>
          </div>

          {/* Preview */}
          <div className="mt-5">
            <div
              className={cn(
                "relative mx-auto overflow-hidden rounded-2xl border border-white/10 bg-black",
                isPortrait || tab === "photo"
                  ? "aspect-[9/16] max-w-[320px]"
                  : "aspect-video w-full",
              )}
            >
              {tab === "phone" ? (
                <PhonePanel />
              ) : tab === "photo" ? (
                <PhotoPanel url={photoUrl} onPick={onPhotoPick} />
              ) : (
                <>
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className={cn(
                      "h-full w-full -scale-x-100 object-cover transition-opacity",
                      ready ? "opacity-100" : "opacity-0",
                    )}
                  />
                  {/* Recording-preview badge */}
                  {ready && (
                    <span className="absolute right-3 top-3 flex items-center gap-1.5 rounded-full bg-black/50 px-2.5 py-1 text-xs font-medium text-white backdrop-blur">
                      <span className="h-2 w-2 rounded-full bg-red-500" />
                      Pré-visualização
                    </span>
                  )}
                  {status === "loading" && <Overlay icon={Loader2} spin text="Conectando à câmera…" />}
                  {status === "denied" && (
                    <Overlay
                      icon={CameraOff}
                      text="Acesso à câmera e ao microfone negado."
                      action={{ label: "Tentar novamente", onClick: () => startStream() }}
                    />
                  )}
                  {status === "error" && (
                    <Overlay
                      icon={CameraOff}
                      text={errMsg}
                      action={{ label: "Tentar novamente", onClick: () => startStream() }}
                    />
                  )}
                </>
              )}
            </div>

            {/* Camera configuration row */}
            {tab === "webcam" && (
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                <Dropdown
                  value={aspect}
                  options={ASPECTS}
                  onChange={(v) => handleAspect(v as Aspect)}
                  icon={Monitor}
                  side="top"
                />
                <Dropdown
                  value={cameraId}
                  options={cameras}
                  onChange={handleCamera}
                  icon={Camera}
                  side="top"
                  placeholder="Câmera"
                  emptyLabel="Nenhuma câmera"
                />
                <Dropdown
                  value={micId}
                  options={mics}
                  onChange={handleMic}
                  icon={Mic}
                  side="top"
                  placeholder="Microfone"
                  emptyLabel="Nenhum microfone"
                  meter={ready ? <AudioMeter stream={activeStream} /> : null}
                />
              </div>
            )}
          </div>

          {/* Photo name (photo tab) or script language (recording tabs) */}
          {tab === "photo" ? (
            <div className="mx-auto mt-6 max-w-md">
              <label className="block text-center text-sm text-zinc-400">
                Nome do avatar
              </label>
              <input
                value={photoName}
                onChange={(e) => setPhotoName(e.target.value)}
                placeholder="Ex.: Maria CEO"
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder:text-zinc-500 focus:border-accent/60 focus:outline-none focus:ring-1 focus:ring-accent/40"
              />
              <p className="mt-2 text-center text-xs text-zinc-500">
                Você escolhe a voz na próxima etapa. Aceita JPG, PNG, WebP, HEIC e mais.
              </p>
              {photoErr && <p className="mt-3 text-center text-sm text-red-300">{photoErr}</p>}
            </div>
          ) : (
            <div className="mt-6 flex items-center justify-center gap-2 text-sm text-zinc-400">
              <Languages className="h-4 w-4 text-zinc-500" />
              Vamos exibir um roteiro na tela em
              <Dropdown
                value={lang}
                options={LANGS}
                onChange={setLang}
                side="top"
                align="end"
              />
            </div>
          )}

          {/* Footer actions */}
          <div className="mt-8 flex items-center justify-center gap-6">
            <button
              onClick={close}
              className="text-sm font-medium text-zinc-300 transition-colors hover:text-white"
            >
              Voltar
            </button>
            {tab === "photo" ? (
              <button
                disabled={!photoFile || creatingPhoto}
                onClick={createFromPhoto}
                className={cn(
                  "flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold transition-colors",
                  photoFile && !creatingPhoto
                    ? "bg-accent text-obsidian hover:bg-accent-strong"
                    : "cursor-not-allowed bg-white/10 text-zinc-500",
                )}
              >
                {creatingPhoto ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                {creatingPhoto ? "Criando…" : "Criar avatar"}
              </button>
            ) : (
              <button
                disabled={tab === "webcam" && !ready}
                onClick={() => setStep("tips")}
                className={cn(
                  "flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold transition-colors",
                  tab === "phone" || ready
                    ? "bg-accent text-obsidian hover:bg-accent-strong"
                    : "cursor-not-allowed bg-white/10 text-zinc-500",
                )}
              >
                <CheckCircle2 className="h-4 w-4" />
                Estou pronto
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );

  return (
    <>
      {(step === "config" || step === "tips") && config}

      {step === "tips" && (
        <RecordingTips onClose={() => setStep("config")} onStart={() => setStep("recording")} />
      )}

      {step === "recording" && (
        <AvatarRecorder
          stream={activeStream}
          aspect={aspect}
          lang={lang}
          onClose={() => setStep("config")}
          onFinish={handleFinish}
        />
      )}

      {step === "review" && (
        <RecordReview
          url={recordedUrl}
          aspect={aspect}
          onRetake={() => setStep("recording")}
          onClose={close}
          onCreate={handleCreate}
        />
      )}
    </>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Video;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center justify-center gap-2 rounded-full py-2 text-sm font-medium transition-colors",
        active ? "bg-white/10 text-white" : "text-zinc-400 hover:text-zinc-200",
      )}
    >
      <Icon className="h-4 w-4" />
      {children}
    </button>
  );
}

function Overlay({
  icon: Icon,
  text,
  spin,
  action,
}: {
  icon: typeof Loader2;
  text: string;
  spin?: boolean;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 px-6 text-center">
      <Icon className={cn("h-7 w-7 text-zinc-300", spin && "animate-spin")} />
      <p className="text-sm text-zinc-300">{text}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-obsidian hover:bg-accent-strong"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

function PhotoPanel({
  url,
  onPick,
}: {
  url: string | null;
  onPick: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <label className="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-3 px-6 text-center transition-colors hover:bg-white/5">
      {url ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt="Pré-visualização" className="absolute inset-0 h-full w-full object-cover" />
          <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs font-medium text-white backdrop-blur">
            Trocar foto
          </span>
        </>
      ) : (
        <>
          <ImagePlus className="h-8 w-8 text-zinc-400" />
          <p className="text-sm text-zinc-300">Clique para carregar uma foto</p>
          <p className="text-xs text-zinc-500">JPG, PNG, WebP, HEIC, GIF…</p>
        </>
      )}
      <input
        type="file"
        accept="image/*,.heic,.heif,.avif,.webp,.bmp,.tiff"
        className="hidden"
        onChange={onPick}
      />
    </label>
  );
}

function PhonePanel() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
      <Smartphone className="h-8 w-8 text-zinc-400" />
      <p className="text-sm text-zinc-300">
        Escaneie o QR code com o celular para gravar com a câmera dele.
      </p>
      <div className="mt-1 h-28 w-28 rounded-xl bg-white/10" />
      <p className="text-xs text-zinc-500">Geração de QR em construção.</p>
    </div>
  );
}
