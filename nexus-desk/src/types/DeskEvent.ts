export type DeskEvent = 
  | PhaseEvent
  | LogEvent
  | MetricsEvent
  | StatusEvent;

export type PhaseEvent = {
  kind: "phase.start" | "phase.complete" | "phase.error";
  taskId: string;
  phase: "P" | "X" | "D" | "R" | "A" | "C";
  status?: "success" | "fail";
  ts: string;
};

export type LogEvent = {
  kind: "log.line";
  taskId: string;
  line: string;
  ansi: boolean;
  ts: string;
};

export type MetricsEvent = {
  kind: "metrics.update";
  taskId: string;
  tokens: number;
  latency: number;
  cost?: number;
  ts: string;
};

export type StatusEvent = {
  kind: "status.update";
  taskId: string;
  normalizedStatus: string;
  locked: boolean;
  ts: string;
};
