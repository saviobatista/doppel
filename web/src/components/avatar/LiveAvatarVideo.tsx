"use client";

import { useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * The "live" avatar player. It plays the greeting ("...what are we gonna do
 * today?") once, then cross-fades into the silent idle loop so the avatar keeps
 * eye contact and blinks while waiting for the user — no abrupt jump cut.
 *
 * The greeting starts muted (browsers block autoplay with sound); a speaker
 * toggle lets the user hear it and replays the greeting when un-muting.
 */
export function LiveAvatarVideo({
  helloUrl,
  idleUrl,
  posterUrl,
}: {
  helloUrl: string | null;
  idleUrl: string | null;
  posterUrl?: string | null;
}) {
  const helloRef = useRef<HTMLVideoElement>(null);
  const idleRef = useRef<HTMLVideoElement>(null);
  const [onIdle, setOnIdle] = useState(false);
  const [muted, setMuted] = useState(true);

  // Photo avatars (and any voiceless avatar) have no greeting: just loop the
  // idle "live" clip, or fall back to the still poster if even that is missing.
  if (!helloUrl) {
    return (
      <div className="relative aspect-[9/16] w-full bg-black">
        {idleUrl ? (
          <video
            src={idleUrl}
            autoPlay
            muted
            loop
            playsInline
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : posterUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={posterUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
        ) : null}
      </div>
    );
  }

  const handleHelloEnded = () => {
    if (!idleUrl) {
      // No idle clip: gently loop the greeting (muted) as a fallback.
      const h = helloRef.current;
      if (h) {
        h.currentTime = 0;
        h.muted = true;
        setMuted(true);
        h.play().catch(() => {});
      }
      return;
    }
    const idle = idleRef.current;
    if (idle) {
      idle.currentTime = 0;
      idle.play().catch(() => {});
    }
    setOnIdle(true);
  };

  const toggleSound = () => {
    const next = !muted;
    setMuted(next);
    const h = helloRef.current;
    if (!next && h) {
      // Un-muting: replay the greeting from the top so it's actually heard.
      setOnIdle(false);
      h.currentTime = 0;
      h.muted = false;
      h.play().catch(() => {});
    }
  };

  return (
    <div className="relative aspect-[9/16] w-full bg-black">
      <video
        ref={helloRef}
        src={helloUrl}
        autoPlay
        muted={muted}
        playsInline
        onEnded={handleHelloEnded}
        className={cn(
          "absolute inset-0 h-full w-full object-cover transition-opacity duration-500",
          onIdle ? "opacity-0" : "opacity-100",
        )}
      />
      {idleUrl && (
        <video
          ref={idleRef}
          src={idleUrl}
          muted
          loop
          playsInline
          className={cn(
            "absolute inset-0 h-full w-full object-cover transition-opacity duration-500",
            onIdle ? "opacity-100" : "opacity-0",
          )}
        />
      )}

      <button
        onClick={toggleSound}
        aria-label={muted ? "Ativar som" : "Desativar som"}
        className="absolute bottom-3 right-3 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur transition-colors hover:bg-black/75"
      >
        {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
      </button>
    </div>
  );
}
