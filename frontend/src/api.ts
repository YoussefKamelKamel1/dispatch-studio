export type Channel = "linkedin" | "newsletter" | "website";
export type Draft = { title: string; body: string };
export type Content = Record<Channel, Draft>;
export type Job = {
  id: string;
  item_id: string;
  revision: number;
  channel: string;
  status: string;
  attempts: number;
  error: string | null;
  url: string | null;
  updated_at: string;
  title?: string;
  reviewer?: string;
  approved_at?: string;
};
export type Item = {
  id: string;
  title: string;
  source: string;
  project_id: string;
  project_name: string;
  project_color: string;
  update_type: string;
  audience: string;
  cta: string;
  status: string;
  revision: number;
  provider: string;
  warnings: string[];
  error: string | null;
  created_at: string;
  updated_at: string;
  content: Content | null;
  channels: string[];
  jobs: Job[];
  approvals: {
    id: string;
    revision: number;
    reviewer: string;
    status: string;
    created_at: string;
  }[];
};
export type Source = {
  title: string;
  source: string;
  project_id: string;
  update_type: string;
  audience: string;
  cta: string;
};
export type Config = {
  projects: { id: string; name: string; color: string }[];
  ai_mode: string;
  model: string;
  sample: Source;
  fail_next: Record<string, boolean>;
  connections: Connection[];
  ai_connection: AIConnection;
};
export type ConnectionCheck = {
  status: string;
  detail: string;
  checked_at?: string;
};
export type AIConnection = {
  provider: string;
  mode: string;
  model: string;
  key_configured: boolean;
  status: string;
  check: ConnectionCheck | null;
};
export type Connection = {
  id: string;
  provider: string;
  target: string;
  account?: string;
  version?: string;
  configured: boolean;
  status: string;
  detail: string;
  check: ConnectionCheck | null;
};
export function destinationLabel(connection?: Connection) {
  if (!connection || connection.provider === "local") return "Local test CMS";
  if (connection.provider === "sandbox") return "Social publishing sandbox";
  if (connection.provider === "wordpress")
    return "WordPress · " + (connection.target || "setup required");
  return "LinkedIn · " + (connection.target || "setup required");
}
export type Activity = {
  id: string;
  item_id: string | null;
  action: string;
  detail: string;
  created_at: string;
};
export type Session = { email: string; name: string; csrf: string };
export type Revision = {
  revision: number;
  content: Content;
  channels: string[];
  created_at: string;
};
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "The request could not be completed. Check your input and try again.",
    );
  }
  return response.json();
}
export const channelNames: Record<string, string> = {
  website: "Website",
  linkedin: "LinkedIn",
  newsletter: "Newsletter",
};
export function date(value: string) {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
export function words(value: string) {
  return value.trim().split(/\s+/).filter(Boolean).length;
}
