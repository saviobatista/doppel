import { sendFeedback } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";
import { playerScene } from "./hello";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `
    <div class="row">
      <button id="up">${STR.thumbsUp}</button>
      <button id="down">${STR.thumbsDown}</button>
    </div>`;
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
