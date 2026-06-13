import { deleteMe, fetchGallery } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  const items = await fetchGallery();
  stage.innerHTML = `
    <div class="gallery-grid">
      ${items.map((i) => `<video src="${i.fast_url}" controls playsinline></video>`).join("")}
    </div>
    <div class="row">
      ${ctx.avatarId ? `<button id="new">${STR.newVideo}</button>` : ""}
      <button id="del">${STR.deleteMe}</button>
    </div>`;
  return new Promise<State>((resolve) => {
    stage.querySelector("#new")?.addEventListener("click", () => resolve("briefing"), { once: true });
    stage.querySelector("#del")!.addEventListener("click", async () => {
      await deleteMe();
      ctx.avatarId = null;
      resolve("idle");
    }, { once: true });
  });
}
