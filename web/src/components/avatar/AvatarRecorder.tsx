"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { avatarScript, makeUniqueCode } from "@/lib/avatarScript";
import { cn } from "@/lib/cn";

interface AvatarRecorderProps {
  stream: MediaStream | null;
  aspect: "landscape" | "portrait";
  lang: string;
  onClose: () => void;
  onFinish: (blob: Blob, meta: { code: number; durationMs: number }) => void;
}

const COUNTDOWN_S = 5; // lead-in before recording starts
const MAX_RECORD_S = 30; // hard stop
const SCROLL_S = 30; // teleprompter enters from the bottom and exits the top over this window

type Phase = "countdown" | "recording";

export function AvatarRecorder({ stream, aspect, lang, onClose, onFinish }: AvatarRecorderProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLParagraphElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const finishingRef = useRef(false);
  const startedAtRef = useRef(0);

  const [phase, setPhase] = useState<Phase>("countdown");
  const [count, setCount] = useState(COUNTDOWN_S);
  const [elapsed, setElapsed] = useState(0);
  const [code] = useState(makeUniqueCode);
  const [script] = useState(() => avatarScript(lang, code));

  // Attach the live stream to the fullscreen preview.
  useEffect(() => {
    if (videoRef.current && stream) videoRef.current.srcObject = stream;
  }, [stream]);

  // Countdown lead-in, then flip to recording.
  useEffect(() => {
    const iv = setInterval(() => {
      setCount((c) => {
        if (c <= 1) {
          clearInterval(iv);
          setPhase("recording");
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  // Start recording + timer + teleprompter once the countdown ends.
  useEffect(() => {
    if (phase !== "recording" || !stream) return;

    const mime =
      ["video/webm;codecs=vp9", "video/webm", "video/mp4"].find((m) =>
        typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(m),
      ) ?? "";

    let rec: MediaRecorder | null = null;
    try {
      rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorderRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        if (!finishingRef.current) return;
        const blob = new Blob(chunksRef.current, { type: rec?.mimeType || "video/webm" });
        onFinish(blob, { code, durationMs: Date.now() - startedAtRef.current });
      };
      rec.start(1000);
      startedAtRef.current = Date.now();
    } catch {
      startedAtRef.current = Date.now();
    }

    const timer = setInterval(() => {
      const el = Math.floor((Date.now() - startedAtRef.current) / 1000);
      setElapsed(el);
      if (el >= MAX_RECORD_S) {
        clearInterval(timer);
        finishingRef.current = true;
        const r = recorderRef.current;
        if (r && r.state !== "inactive") r.stop();
        else
          onFinish(new Blob(chunksRef.current, { type: "video/webm" }), {
            code,
            durationMs: Date.now() - startedAtRef.current,
          });
      }
    }, 250);

    let raf = 0;
    const begin = performance.now();
    const scrollTick = (now: number) => {
      const box = boxRef.current;
      const inner = innerRef.current;
      if (box && inner) {
        // Start with the text just below the box, then roll it up and fully off
        // the top — entering from the bottom and leaving at the top over SCROLL_S.
        const dist = inner.scrollHeight + box.clientHeight;
        const progress = Math.min(1, (now - begin) / 1000 / SCROLL_S);
        const y = box.clientHeight - progress * dist;
        inner.style.transform = `translateY(${y}px)`;
      }
      raf = requestAnimationFrame(scrollTick);
    };
    raf = requestAnimationFrame(scrollTick);

    return () => {
      clearInterval(timer);
      cancelAnimationFrame(raf);
      if (rec && rec.state !== "inactive") {
        try {
          rec.stop();
        } catch {
          /* noop */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, stream]);

  const finish = () => {
    finishingRef.current = true;
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
    else
      onFinish(new Blob(chunksRef.current, { type: "video/webm" }), {
        code,
        durationMs: Date.now() - startedAtRef.current,
      });
  };

  const close = () => {
    finishingRef.current = false;
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      try {
        rec.stop();
      } catch {
        /* noop */
      }
    }
    onClose();
  };

  const remaining = Math.max(0, MAX_RECORD_S - elapsed);
  const mmss = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`;
  const isPortrait = aspect === "portrait";
  const recording = phase === "recording";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-800">
      {/* Video stage: cover in landscape, centered with grey bars in portrait */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className={cn(
          "-scale-x-100 bg-black object-cover",
          isPortrait ? "h-full aspect-[9/16]" : "h-full w-full",
        )}
      />

      {/* Countdown lead-in */}
      <AnimatePresence>
        {!recording && (
          <motion.div
            key="countdown"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/40 backdrop-blur-sm"
          >
            <p className="mb-4 text-sm font-medium uppercase tracking-widest text-zinc-300">
              Prepare-se
            </p>
            <motion.span
              key={count}
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="text-8xl font-bold tabular-nums text-white [text-shadow:0_2px_12px_rgba(0,0,0,0.6)]"
            >
              {count}
            </motion.span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top-right: blinking record indicator + remaining time, and close */}
      <div className="absolute right-5 top-5 z-20 flex items-center gap-3">
        {recording && (
          <span className="flex items-center gap-2 rounded-full bg-black/55 px-3 py-1.5 text-sm font-semibold tabular-nums text-white backdrop-blur">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
            {mmss}
          </span>
        )}
        <button
          onClick={close}
          aria-label="Fechar gravação"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur transition-colors hover:bg-black/75"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Teleprompter overlay */}
      {recording && (
        <div
          ref={boxRef}
          className="pointer-events-none absolute left-1/2 top-8 z-20 max-h-[28%] w-[min(90%,760px)] -translate-x-1/2 overflow-hidden rounded-2xl bg-black/45 px-7 py-5 backdrop-blur-sm"
        >
          <p
            ref={innerRef}
            className="text-center text-2xl font-medium leading-relaxed text-white [text-shadow:0_1px_4px_rgba(0,0,0,0.5)] will-change-transform"
          >
            {script}
          </p>
        </div>
      )}

      {/* Finish */}
      {recording && (
        <button
          onClick={finish}
          className="absolute bottom-10 left-1/2 z-20 -translate-x-1/2 rounded-full bg-accent px-7 py-3 text-sm font-semibold text-obsidian shadow-lg shadow-black/40 transition-colors hover:bg-accent-strong"
        >
          Gravação finalizada
        </button>
      )}
    </div>
  );
}
