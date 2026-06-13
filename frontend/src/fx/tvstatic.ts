export async function tvStatic(parent: HTMLElement, durationMs = 900): Promise<void> {
  const canvas = document.createElement("canvas");
  canvas.className = "fx";
  parent.appendChild(canvas);
  const ctx = canvas.getContext("2d")!;
  const start = performance.now();
  return new Promise((resolve) => {
    const tick = (now: number) => {
      const progress = (now - start) / durationMs;
      if (progress >= 1) {
        canvas.remove();
        resolve();
        return;
      }
      canvas.width = 270;
      canvas.height = 480;
      const img = ctx.createImageData(canvas.width, canvas.height);
      const intensity = 255 * (1 - progress); // estabiliza ao longo do tempo
      for (let i = 0; i < img.data.length; i += 4) {
        const v = Math.random() * intensity;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}
