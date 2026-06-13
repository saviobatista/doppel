import { consumeSse } from "../api";
import { Gears } from "../fx/gears";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  ctx.stage.innerHTML = "";
  const gears = new Gears(ctx.stage);
  gears.setLabel(STR.generatingSteps.scripting);
  gears.start();
  let failed = false;
  await new Promise<void>((resolve) => {
    consumeSse(`/v1/videos/${ctx.videoId}/events`, (event, data) => {
      if (event === "progress") {
        const step = data.step as string;
        gears.setLabel(STR.generatingSteps[step] ?? step);
      }
      if (event === "status" && data.fast_url) {
        ctx.fastUrl = data.fast_url as string;
        resolve();
      }
      if (event === "fast_ready") {
        ctx.fastUrl = data.fast_url as string;
        resolve();
      }
      if (event === "failed") { failed = true; resolve(); }
    })
      .then(resolve)
      .catch(() => { failed = true; resolve(); });
  });
  gears.stop();
  return failed || !ctx.fastUrl ? "error" : "reveal";
}
