export interface Server {
  id: number;
  hostname: string;
  ip_address: string;
  port: number;
  status: "active" | "inactive" | "pending" | "unreachable";
  mode: "linux-fleet" | "windows-independent";
  os: "linux" | "windows";
  last_seen: string | null;
}

export interface SystemStats {
  cpu: { percent: number; per_cpu: number[]; count: number; freq_mhz: number | null };
  memory: { total: number; available: number; used: number; percent: number };
  disk: { total: number; used: number; free: number; percent: number };
  network: { bytes_sent: number; bytes_recv: number; packets_sent: number; packets_recv: number };
}

export interface FileEntry {
  name: string;
  type: "file" | "directory";
  size: number;
  modified: number;
}

export interface DirectoryListing {
  type: "directory";
  path: string;
  entries: FileEntry[];
}

export interface ServiceInfo {
  name: string;
  status: string;
  sub_status: string;
  description: string;
}

export interface LogResponse {
  path: string;
  total_lines: number;
  offset: number;
  limit: number;
  lines: string[];
}

export interface User {
  id: number;
  username: string;
  role: "admin" | "operator" | "viewer";
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  agent_id: number | null;
  action: string;
  details: string | null;
  timestamp: string;
}
