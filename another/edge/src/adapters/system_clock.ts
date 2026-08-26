import type { ClockPort } from "../ports/clock_port.js";

/** SystemClock — тривиальный адаптер ClockPort поверх Date.now(). */
export class SystemClock implements ClockPort {
  nowUnixSeconds(): number {
    return Math.floor(Date.now() / 1000);
  }
}
