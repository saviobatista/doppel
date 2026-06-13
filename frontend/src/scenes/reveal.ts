import { tvStatic } from "../fx/tvstatic";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { playerScene } from "./hello";

export async function run(ctx: AppCtx): Promise<State> {
  ctx.stage.innerHTML = "";
  await tvStatic(ctx.stage, 900);
  await playerScene(ctx, ctx.fastUrl!);
  return "feedback";
}
