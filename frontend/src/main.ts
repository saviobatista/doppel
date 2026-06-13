import "./style.css";
import { ensureSession } from "./api";
import { Machine, type State } from "./machine";
import { STR } from "./strings";
import * as briefing from "./scenes/briefing";
import * as feedback from "./scenes/feedback";
import * as gallery from "./scenes/gallery";
import * as generating from "./scenes/generating";
import * as hello from "./scenes/hello";
import * as permission from "./scenes/permission";
import * as processing from "./scenes/processing";
import * as reading from "./scenes/reading";
import * as reveal from "./scenes/reveal";

export interface AppCtx {
  stage: HTMLElement;
  stream: MediaStream | null;
  avatarId: string | null;
  videoId: string | null;
  helloUrl: string | null;
  feedbackUrl: string | null;
  fastUrl: string | null;
}

const stage = document.getElementById("stage")!;
const ctx: AppCtx = {
  stage, stream: null, avatarId: null, videoId: null,
  helloUrl: null, feedbackUrl: null, fastUrl: null,
};

async function idleScene(): Promise<State> {
  stage.innerHTML = `
    <h1>doppel</h1>
    <div class="row">
      <button id="start">${STR.start}</button>
      <button id="gal">${STR.galleryLink}</button>
    </div>`;
  return new Promise((resolve) => {
    stage.querySelector("#start")!.addEventListener("click", () => resolve("permission"), { once: true });
    stage.querySelector("#gal")!.addEventListener("click", () => resolve("gallery"), { once: true });
  });
}

async function errorScene(): Promise<State> {
  stage.innerHTML = `
    <p class="reading-text">${STR.genericError}</p>
    <button id="retry">${STR.retry}</button>`;
  return new Promise((resolve) => {
    stage.querySelector("#retry")!.addEventListener("click", () => resolve("idle"), { once: true });
  });
}

const SCENES: Record<State, (ctx: AppCtx) => Promise<State>> = {
  idle: idleScene,
  permission: permission.run,
  reading: reading.run,
  processing: processing.run,
  hello: hello.run,
  briefing: briefing.run,
  generating: generating.run,
  reveal: reveal.run,
  feedback: feedback.run,
  gallery: gallery.run,
  error: errorScene,
};

async function fadeTo(next: () => Promise<State>): Promise<State> {
  stage.classList.add("faded");
  await new Promise((r) => setTimeout(r, 600));
  // scenes set their innerHTML synchronously before their first await, so the
  // new DOM is in place here; paint it one frame while still faded, then fade in.
  const p = next();
  await new Promise((r) => requestAnimationFrame(r));
  stage.classList.remove("faded");
  return p;
}

async function loop(): Promise<void> {
  await ensureSession();
  const machine = new Machine();
  for (;;) {
    const scene = SCENES[machine.state];
    let next: State;
    try {
      next = await fadeTo(() => scene(ctx));
    } catch (err) {
      console.error("scene error", err);
      next = "error";
    }
    try {
      machine.go(next);
    } catch (err) {
      console.error("illegal transition", err);
      machine.state = "error";
    }
  }
}

loop().catch((err) => {
  console.error("fatal", err);
  stage.innerHTML = `<p class="reading-text">${STR.genericError}</p>`;
});
