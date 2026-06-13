import { downloadVideo, sendFeedback } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";
import { playerScene } from "./hello";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `
    <video class="player" src="${ctx.fastUrl}" playsinline controls></video>
    <div class="row">
      <button id="dl">${STR.download}</button>
    </div>
    <div class="row" id="rate" hidden>
      <button id="up">${STR.thumbsUp}</button>
      <button id="down">${STR.thumbsDown}</button>
    </div>`;
  const video = stage.querySelector("video")!;
  const rate = stage.querySelector("#rate") as HTMLElement;
  // the rating only appears once the user has watched the video through
  video.addEventListener("ended", () => { rate.hidden = false; }, { once: true });
  video.play().catch(() => {}); // autoplay may be blocked; controls let the user play
  stage.querySelector("#dl")!.addEventListener("click", () => {
    void downloadVideo(ctx.videoId!);
  });

  const rating = await new Promise<"up" | "down">((resolve) => {
    stage.querySelector("#up")!.addEventListener("click", () => resolve("up"), { once: true });
    stage.querySelector("#down")!.addEventListener("click", () => resolve("down"), { once: true });
  });
  const result = await sendFeedback(ctx.videoId!, rating);
  if (rating === "up") return "gallery";
  if (ctx.feedbackUrl) await playerScene(ctx, ctx.feedbackUrl);
  ctx.videoId = result.video_id; // novo video da regeneracao
  return "generating";
}
