const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function typewriter(
  el: HTMLElement, text: string, msPerChar = 45,
): Promise<void> {
  el.textContent = "";
  for (const ch of text) {
    el.textContent += ch;
    await sleep(msPerChar);
  }
}
