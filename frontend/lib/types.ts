export type Definition = {
  name: string;
  version: number;
  description: string;
  tasks: {
    name: string;
    taskReferenceName: string;
    type: string;
    inputParameters: Record<string, unknown>;
  }[];
  [key: string]: unknown;
};
export type Run = {
  workflowId: string;
  workflowType?: string;
  workflowName?: string;
  status: string;
  startTime: number | string;
  endTime?: number | string;
  executionTime?: number;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  tasks?: Task[];
  reasonForIncompletion?: string;
};
export type Task = {
  taskId: string;
  taskDefName: string;
  referenceTaskName: string;
  status: string;
  retryCount: number;
  startTime: number;
  endTime: number;
  workerId?: string;
  inputData: Record<string, unknown>;
  outputData: Record<string, unknown>;
  reasonForIncompletion?: string;
};
export type Infrastructure = {
  observedAt: number;
  engine: { status: string; latencyMs: number | null };
  api: { status: string };
  workers: {
    name: string;
    status: string;
    lastPollTime: number | null;
    pollers: unknown[];
  }[];
  gemini: {
    configured: boolean;
    enabled: boolean;
    model: string;
    status: string;
  };
  storage: { type: string; status: string };
};

export type Cluster = {
  id: string;
  name: string;
  kind: "logical" | "provider" | "local";
  provider: string | null;
  description: string;
  project_count: number;
  service_count: number;
  down_count: number;
  open_incidents: number;
  created_at: string;
};

export type Environment = {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  kind: "development" | "staging" | "production" | "custom";
  service_count: number;
};

export type ServiceStatus =
  | "healthy"
  | "degraded"
  | "down"
  | "unknown"
  | "disabled";

export type Service = {
  id: string;
  project_id: string;
  project_name: string;
  environment_id: string | null;
  environment_name: string | null;
  environment_kind: string | null;
  connector_id: string | null;
  name: string;
  kind: "web" | "api" | "database" | "worker" | "queue" | "cache" | "external";
  provider: "http" | "railway" | "github" | "docker" | "manual";
  health_url: string | null;
  monitoring_enabled: boolean;
  check_interval_seconds: number;
  timeout_seconds: number;
  expected_status: number;
  failure_threshold: number;
  recovery_threshold: number;
  current_status: ServiceStatus;
  status_changed_at: string | null;
  last_checked_at: string | null;
  last_ok_at: string | null;
  consecutive_failures: number;
  consecutive_successes: number;
  last_error: string | null;
  observations_24h: number;
  external_ref: Record<string, unknown>;
};

export type Observation = {
  id: number;
  service_id: string;
  observed_at: string;
  status: ServiceStatus;
  source: "http" | "provider" | "agent" | "manual";
  latency_ms: number | null;
  http_status: number | null;
  message: string;
  evidence: Record<string, unknown>;
};

export type Project = {
  id: string;
  name: string;
  slug: string;
  description: string;
  cluster_id: string | null;
  cluster_name: string | null;
  cluster_kind: string | null;
  repo_url: string | null;
  repo_branch: string | null;
  status: ServiceStatus;
  service_count: number;
  healthy_count: number;
  degraded_count: number;
  down_count: number;
  unknown_count: number;
  disabled_count: number;
  open_incidents: number;
  environment_count: number;
  last_deployed_at: string | null;
  created_at: string;
  environments?: Environment[];
  services?: Service[];
  deployments?: Deployment[];
  incidents?: Incident[];
};

export type Deployment = {
  id: string;
  project_id: string;
  project_name: string;
  environment_id: string | null;
  environment_name: string | null;
  service_id: string | null;
  service_name: string | null;
  provider: string;
  external_id: string | null;
  version: string | null;
  commit_sha: string;
  status: string;
  url: string | null;
  detail: Record<string, unknown>;
  deployed_at: string;
};

export type IncidentEvent = {
  id: number;
  incident_id: string;
  at: string;
  kind: string;
  actor: string;
  message: string;
  data: Record<string, unknown>;
};

export type Incident = {
  id: string;
  project_id: string;
  project_name: string;
  service_id: string;
  service_name: string;
  service_status: ServiceStatus;
  health_url: string | null;
  title: string;
  severity: "critical" | "major" | "minor";
  status: "open" | "acknowledged" | "resolved";
  opened_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  detection: { observation?: Observation; previous_status?: string; threshold?: number };
  resolution_note: string | null;
  event_count: number;
  events?: IncidentEvent[];
  observations?: Observation[];
  notifications?: {
    id: number;
    channel: string;
    status: string;
    error: string | null;
    created_at: string;
  }[];
};

export type Connector = {
  id: string;
  provider: "railway" | "github" | "docker";
  name: string;
  config: Record<string, unknown>;
  status: "unconfigured" | "connected" | "error";
  last_validated_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  created_at: string;
};

export type Alert = {
  id: string;
  name: string;
  channel: "webhook";
  project_id: string | null;
  project_name: string | null;
  min_severity: "critical" | "major" | "minor";
  cooldown_seconds: number;
  enabled: boolean;
  last_notified_at: string | null;
};

export type Dashboard = {
  totals: {
    projects: number;
    services: number;
    healthy: number;
    degraded: number;
    down: number;
    unknown: number;
    disabled: number;
    active_incidents: number;
    connectors: number;
    stale: number;
  };
  clusters: { id: string; name: string; kind: string; projects: number; down: number }[];
  environments: { kind: string; services: number; down: number }[];
  needs_attention: {
    id: string;
    name: string;
    current_status: ServiceStatus;
    last_checked_at: string | null;
    last_error: string | null;
    project_id: string;
    project_name: string;
    environment_name: string | null;
  }[];
  incidents: Incident[];
  deployments: Deployment[];
  projects: Project[];
  stale: {
    id: string;
    name: string;
    last_checked_at: string | null;
    project_name: string;
    check_interval_seconds: number;
  }[];
  workflows: {
    status: "available" | "unavailable";
    failed: Run[];
    total_hits: number | null;
  };
  observed_at: string;
};
