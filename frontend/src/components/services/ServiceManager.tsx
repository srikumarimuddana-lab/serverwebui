"use client";

import { useEffect, useState } from "react";
import { fetchServices, controlService } from "@/lib/api";
import type { Server, ServiceInfo } from "@/types";
import { Play, Square, RotateCcw } from "lucide-react";

interface Props { server: Server; }

export default function ServiceManager({ server }: Props) {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try { const data = await fetchServices(server); setServices(data); } catch {}
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function handleAction(name: string, action: string) {
    setActionLoading(`${name}-${action}`);
    try { await controlService(server, name, action); await load(); } catch {}
    setActionLoading(null);
  }

  const filtered = services.filter(
    (s) => s.name.toLowerCase().includes(filter.toLowerCase()) || s.description.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <input type="text" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter services..."
        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500" />
      <div className="bg-gray-900 border border-gray-800 rounded-lg divide-y divide-gray-800">
        {loading ? <p className="text-gray-500 text-center py-8">Loading services...</p> :
         filtered.length === 0 ? <p className="text-gray-500 text-center py-8">No services found</p> :
         filtered.map((svc) => (
          <div key={svc.name} className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-gray-200 text-sm font-medium">{svc.name}</p>
              <p className="text-gray-500 text-xs">{svc.description}</p>
            </div>
            <div className="flex items-center gap-3">
              <span className={`text-xs px-2 py-0.5 rounded ${svc.status === "active" ? "bg-green-900 text-green-400" : "bg-gray-800 text-gray-400"}`}>{svc.sub_status}</span>
              <div className="flex gap-1">
                <button onClick={() => handleAction(svc.name, "start")} disabled={actionLoading === `${svc.name}-start`} className="p-1.5 text-gray-400 hover:text-green-400 hover:bg-gray-800 rounded" title="Start"><Play className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleAction(svc.name, "stop")} disabled={actionLoading === `${svc.name}-stop`} className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-800 rounded" title="Stop"><Square className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleAction(svc.name, "restart")} disabled={actionLoading === `${svc.name}-restart`} className="p-1.5 text-gray-400 hover:text-yellow-400 hover:bg-gray-800 rounded" title="Restart"><RotateCcw className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
