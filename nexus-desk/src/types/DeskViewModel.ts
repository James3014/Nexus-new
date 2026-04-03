export interface FieldResolution {
  fieldName: string;
  resolvedValue: string;
  sourceFile: string;
  sourcePath: string;
  sourcePriority: string;
  sourceField: string;
  fallbackUsed: boolean;
  resolutionNote: string;
}

export interface SourceMetadata {
  auditResult?: string;
  acceptance?: string;
  manifest?: string;
  metrics?: string;
}

export interface AvailableActions {
  benchmark: boolean;
  acceptanceCheck: boolean;
  releaseReady: boolean;
  publish: boolean;
}

export interface DeskViewModel {
  taskId: string;
  updatedAt: string;
  workspace: string;
  armorName: string;
  versionLabel: string;
  normalizedStatus: string;
  currentStatusLabel: string;
  terminal: boolean;
  severity: string;
  showCriticalAlert: boolean;
  currentPhase: string;
  taskSummary: string;
  nextActionLabel: string;
  auditPassed: boolean;
  acceptancePassed: boolean;
  releaseReady: boolean;
  canPublish: boolean;
  phaseHealthScore: number;
  phaseHealthSource: string;
  resolutionTrace: FieldResolution[];
  latestLogLines: string[];
  availableActions: AvailableActions;
  evidence: SourceMetadata;
}
