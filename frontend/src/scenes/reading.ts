import { startAvatarUpload } from "../api";
import { typewriter } from "../fx/typewriter";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `<p class="typewriter"></p>`;
  await typewriter(stage.querySelector(".typewriter")!, STR.typewriterIntro);
  await sleep(2500);

  stage.innerHTML = `
    <p><span class="rec-dot"></span></p>
    <p class="reading-text">${STR.readingText}</p>
    <button id="done">${STR.readingDone}</button>`;

  const upload = startAvatarUpload(ctx.stream!);
  ctx.avatarId = await upload.avatarId;

  await new Promise<void>((resolve) => {
    stage.querySelector("#done")!.addEventListener("click", () => resolve(), { once: true });
  });
  await upload.finish();
  ctx.stream!.getTracks().forEach((t) => t.stop());
  ctx.stream = null;
  return "processing";
}
