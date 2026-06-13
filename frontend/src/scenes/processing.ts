import { consumeSse } from "../api";
import { Gears } from "../fx/gears";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  ctx.stage.innerHTML = "";
  const gears = new Gears(ctx.stage);
  gears.setLabel(STR.processing);
  gears.start();
  let failed = false;
  await new Promise<void>((resolve) => {
    consumeSse(`/v1/avatars/${ctx.avatarId}/events`, (event, data) => {
      if (event === "status" && data.hello_url) {
        ctx.helloUrl = data.hello_url as string;
        ctx.feedbackUrl = (data.feedback_url as string) ?? null;
        resolve();
      }
      if (event === "hello_ready") {
        ctx.helloUrl = data.hello_url as string;
        ctx.feedbackUrl = (data.feedback_url as string) ?? null;
        resolve();
      }
      if (event === "failed") { failed = true; resolve(); }
    })
      .then(resolve)
      .catch(() => { failed = true; resolve(); });
  });
  gears.stop();
  return failed || !ctx.helloUrl ? "error" : "hello";
}
