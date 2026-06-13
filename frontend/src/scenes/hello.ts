import type { AppCtx } from "../main";
import type { State } from "../machine";

export function playerScene(ctx: AppCtx, url: string): Promise<void> {
  const stage = ctx.stage;
  stage.innerHTML = "";
  const video = document.createElement("video");
  video.className = "player";
  video.src = url;
  video.playsInline = true;
  video.autoplay = true;
  video.controls = true; // browsers block autoplay-with-audio; let the user play/replay
  stage.appendChild(video);
  return new Promise((resolve) => {
    video.addEventListener("ended", () => resolve(), { once: true });
    video.addEventListener("error", () => resolve(), { once: true });
    // Try to autoplay; if the browser blocks it, do NOT skip ahead - the user
    // presses play via the controls and we advance only when the video ends.
    video.play().catch(() => {});
  });
}

export async function run(ctx: AppCtx): Promise<State> {
  await playerScene(ctx, ctx.helloUrl!);
  return "briefing";
}
