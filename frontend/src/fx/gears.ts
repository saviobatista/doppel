function drawGear(
  ctx: CanvasRenderingContext2D, cx: number, cy: number,
  radius: number, teeth: number, angle: number,
): void {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  ctx.strokeStyle = "#4ad";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(0, 0, radius, 0, Math.PI * 2);
  ctx.stroke();
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    ctx.save();
    ctx.rotate(a);
    ctx.strokeRect(radius - 2, -4, 14, 8);
    ctx.restore();
  }
  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.25, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

export class Gears {
  private canvas: HTMLCanvasElement;
  private raf = 0;
  private label = "";

  constructor(parent: HTMLElement) {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "fx";
    parent.appendChild(this.canvas);
  }

  setLabel(text: string): void {
    this.label = text;
  }

  start(): void {
    const ctx = this.canvas.getContext("2d")!;
    const tick = (t: number) => {
      this.canvas.width = this.canvas.clientWidth;
      this.canvas.height = this.canvas.clientHeight;
      const { width: w, height: h } = this.canvas;
      ctx.clearRect(0, 0, w, h);
      drawGear(ctx, w / 2 - 40, h / 2 - 30, 56, 10, t / 900);
      drawGear(ctx, w / 2 + 48, h / 2 + 42, 38, 8, -t / 600);
      ctx.fillStyle = "#999";
      ctx.font = "16px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText(this.label, w / 2, h / 2 + 140);
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
    this.canvas.remove();
  }
}
