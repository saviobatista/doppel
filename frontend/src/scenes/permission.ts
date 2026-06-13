import type { AppCtx } from "../main";
import type { State } from "../machine";

export async function run(ctx: AppCtx): Promise<State> {
  try {
    ctx.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 540 }, height: { ideal: 960 }, facingMode: "user" },
      audio: true,
    });
    return "reading";
  } catch {
    return "error";
  }
}
