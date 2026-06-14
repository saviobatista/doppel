"use client";

import { useEffect, useRef } from "react";

/**
 * Live microphone input meter. Renders a left-anchored fill that scales with the
 * RMS level of the stream's audio track. Animates via a ref + rAF so it never
 * triggers React re-renders.
 */
export function AudioMeter({ stream }: { stream: MediaStream | null }) {
  const barRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const track = stream?.getAudioTracks()[0];
    if (!stream || !track) return;

    const AudioCtx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx = new AudioCtx();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.8;
    source.connect(analyser);

    const data = new Uint8Array(analyser.fftSize);
    let raf = 0;
    let smoothed = 0;

    // Tuning: ignore ambient noise below the floor, keep a sensitive gain, but
    // cap the visual fill so even loud input never spans the whole pill.
    const NOISE_FLOOR = 0.07;
    const GAIN = 3;
    const MAX_FILL = 0.6; // bar tops out at 60% of the pill width
    const RELEASE = 0.9; // higher = smoother/slower decay (less jumpy)

    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      // Perceptual curve (sqrt) so the bar moves smoothly across the range
      // instead of snapping near the top.
      const norm = Math.min(1, Math.max(0, rms - NOISE_FLOOR) * GAIN);
      const level = Math.sqrt(norm);
      smoothed = Math.max(level, smoothed * RELEASE); // instant attack, smooth release
      const fill = smoothed * MAX_FILL;
      if (barRef.current) barRef.current.style.transform = `scaleX(${fill.toFixed(3)})`;
      raf = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      source.disconnect();
      void ctx.close();
    };
  }, [stream]);

  return (
    <span className="pointer-events-none absolute inset-0 overflow-hidden rounded-full">
      <span
        ref={barRef}
        className="block h-full w-full origin-left bg-accent/30"
        style={{ transform: "scaleX(0)" }}
      />
    </span>
  );
}
