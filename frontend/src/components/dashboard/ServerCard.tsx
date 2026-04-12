"use client";

import type { Server } from "@/types";
import { Monitor, Server as ServerIcon } from "lucide-react";

const statusColors: Record<string, string> = {
  active: "bg-green-500",
  inactive: "bg-gray-500",
  pending: "bg-yellow-500",
  unreachable: "bg-red-500",
};

interface Props {
  server: Server;
  onClick: () => void;
}

export default function ServerCard({ server, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-blue-500 transition-colors text-left w-full"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {server.os === "windows" ? (
            <Monitor className="w-5 h-5 text-blue-400" />
          ) : (
            <ServerIcon className="w-5 h-5 text-green-400" />
          )}
          <h3 className="text-white font-medium">{server.hostname}</h3>
        </div>
        <span className={`w-2.5 h-2.5 rounded-full ${statusColors[server.status] || "bg-gray-500"}`} />
      </div>
      <div className="text-gray-400 text-sm space-y-1">
        <p>{server.ip_address}:{server.port}</p>
        <p className="capitalize">{server.os} &middot; {server.mode.replace("-", " ")}</p>
      </div>
    </button>
  );
}
