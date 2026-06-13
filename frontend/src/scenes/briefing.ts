import { createVideo } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `
    <p><span class="rec-dot"></span></p>
    <p class="reading-text">${STR.briefingPrompt}</p>
    <button id="done">${STR.briefingDone}</button>`;

  let audio: MediaStream;
  try {
    audio = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return "error";
  }
  const recorder = new MediaRecorder(audio);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (ev) => chunks.push(ev.data);
  recorder.start();

  const blob = await new Promise<Blob>((resolve) => {
    stage.querySelector("#done")!.addEventListener("click", () => {
      recorder.onstop = () => resolve(new Blob(chunks, { type: "audio/webm" }));
      recorder.stop();
      audio.getTracks().forEach((t) => t.stop());
    }, { once: true });
  });
  ctx.videoId = await createVideo(ctx.avatarId!, blob);
  return "generating";
}
