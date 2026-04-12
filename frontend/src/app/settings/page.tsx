"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import type { Server } from "@/types";
import { Plus, Trash2, ArrowLeft } from "lucide-react";

export default function SettingsPage() {
  const router = useRouter();
  const [servers, setServers] = useState<Server[]>([]);

  useEffect(() => {
    if (!isAuthenticated()) { router.push("/login"); return; }
    const raw = localStorage.getItem("servers_config");
    if (raw) setServers(JSON.parse(raw));
  }, [router]);

  function save(updated: Server[]) {
    setServers(updated);
    localStorage.setItem("servers_config", JSON.stringify(updated));
  }

  function addServer() {
    const newServer: Server = {
      id: Date.now(), hostname: "", ip_address: "", port: 8420,
      status: "pending", mode: "linux-fleet", os: "linux", last_seen: null,
    };
    save([...servers, newServer]);
  }

  function updateServer(index: number, field: keyof Server, value: string | number) {
    const updated = [...servers];
    (updated[index] as any)[field] = value;
    if (field === "mode") { updated[index].os = value === "windows-independent" ? "windows" : "linux"; }
    save(updated);
  }

  function removeServer(index: number) { save(servers.filter((_, i) => i !== index)); }

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white"><ArrowLeft className="w-5 h-5" /></button>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
        </div>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-white">Servers</h2>
            <button onClick={addServer} className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"><Plus className="w-4 h-4" /> Add Server</button>
          </div>
          {servers.map((server, i) => (
            <div key={server.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-gray-400 text-xs">Hostname</label>
                  <input value={server.hostname} onChange={(e) => updateServer(i, "hostname", e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm" placeholder="my-server" />
                </div>
                <div>
                  <label className="text-gray-400 text-xs">IP Address</label>
                  <input value={server.ip_address} onChange={(e) => updateServer(i, "ip_address", e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm" placeholder="192.168.1.10" />
                </div>
                <div>
                  <label className="text-gray-400 text-xs">Port</label>
                  <input type="number" value={server.port} onChange={(e) => updateServer(i, "port", Number(e.target.value))}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm" />
                </div>
                <div>
                  <label className="text-gray-400 text-xs">Mode</label>
                  <select value={server.mode} onChange={(e) => updateServer(i, "mode", e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm">
                    <option value="linux-fleet">Linux Fleet</option>
                    <option value="windows-independent">Windows Independent</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={() => removeServer(i)} className="text-red-400 hover:text-red-300 p-1"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          ))}
          {servers.length === 0 && <p className="text-gray-500 text-center py-8">No servers configured. Click "Add Server" to get started.</p>}
        </div>
      </div>
    </div>
  );
}
