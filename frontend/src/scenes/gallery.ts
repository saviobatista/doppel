import { deleteMe, downloadVideo, fetchGallery } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = "";
  const items = await fetchGallery();
  stage.innerHTML = `
    <div class="gallery-grid">
      ${items.map((i) => `<div class="gallery-item">
          <video src="${i.fast_url}" controls playsinline></video>
          <button class="dl" data-id="${i.video_id}">${STR.download}</button>
        </div>`).join("")}
    </div>
    <div class="row">
      ${ctx.avatarId ? `<button id="new">${STR.newVideo}</button>` : ""}
      <button id="del">${STR.deleteMe}</button>
    </div>`;
  stage.querySelectorAll<HTMLButtonElement>(".dl").forEach((btn) => {
    btn.addEventListener("click", () => {
      void downloadVideo(btn.dataset.id!);
    });
  });
  return new Promise<State>((resolve) => {
    stage.querySelector("#new")?.addEventListener("click", () => resolve("briefing"), { once: true });
    stage.querySelector("#del")!.addEventListener("click", async () => {
      await deleteMe();
      ctx.avatarId = null;
      resolve("idle");
    }, { once: true });
  });
}
