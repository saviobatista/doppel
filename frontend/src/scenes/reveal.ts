import { tvStatic } from "../fx/tvstatic";
import type { AppCtx } from "../main";
import type { State } from "../machine";

export async function run(ctx: AppCtx): Promise<State> {
  // TV-static reveal, then the result screen (feedback) shows the video with
  // a download button and the rating, so the user watches it there.
  ctx.stage.innerHTML = "";
  await tvStatic(ctx.stage, 900);
  return "feedback";
}
