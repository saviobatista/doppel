export type State =
  | "idle" | "permission" | "reading" | "processing" | "hello"
  | "briefing" | "generating" | "reveal" | "feedback" | "gallery" | "error";

const TRANSITIONS: Record<State, State[]> = {
  idle: ["permission", "gallery"],
  permission: ["reading", "error"],
  reading: ["processing", "error"],
  processing: ["hello", "error"],
  hello: ["briefing"],
  briefing: ["generating", "error"],
  generating: ["reveal", "error"],
  reveal: ["feedback"],
  feedback: ["gallery", "generating"],
  gallery: ["briefing", "idle"],
  error: ["idle"],
};

export class Machine {
  state: State = "idle";
  private listeners: Array<(s: State) => void> = [];

  go(next: State): void {
    if (!TRANSITIONS[this.state].includes(next)) {
      throw new Error(`illegal transition ${this.state} -> ${next}`);
    }
    this.state = next;
    for (const listener of this.listeners) listener(next);
  }

  onChange(cb: (s: State) => void): void {
    this.listeners.push(cb);
  }
}
