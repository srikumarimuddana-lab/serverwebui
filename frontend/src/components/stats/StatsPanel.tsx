"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { getApiBase } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Server, SystemStats } from "@/types";

interface Props { server: Server; }

interface DataPoint { time: string; cpu: number; memory: number; disk: number; }

function formatBytes(bytes: number): string {
  const gb = bytes / (1024 * 1024 * 1024);
  return gb.toFixed(1) + " GB";
}

export default function StatsPanel({ server }: Props) {
  const [current, setCurrent] = useState<SystemStats | null>(null);
  const [history, setHistory] = useState<DataPoint[]>([]);

  useEffect(() => {
    const base = getApiBase(server).replace("http", "ws");
    const token = getToken();
    const ws = new WebSocket(`${base}/stats/stream${token ? `?token=${token}` : ""}`);

    ws.onmessage = (event) => {
      const data: SystemStats = JSON.parse(event.data);
      setCurrent(data);
      setHistory((prev) => {
        const point: DataPoint = { time: new Date().toLocaleTimeString(), cpu: data.cpu.percent, memory: data.memory.percent, disk: data.disk.percent };
        return [...prev, point].slice(-30);
      });
    };

    return () => ws.close();
  }, [server]);

  if (!current) return <p className="text-gray-400">Connecting...</p>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="CPU" value={`${current.cpu.percent.toFixed(1)}%`} sub={`${current.cpu.count} cores`} color="text-blue-400" />
        <StatCard label="Memory" value={`${current.memory.percent.toFixed(1)}%`} sub={`${formatBytes(current.memory.used)} / ${formatBytes(current.memory.total)}`} color="text-green-400" />
        <StatCard label="Disk" value={`${current.disk.percent.toFixed(1)}%`} sub={`${formatBytes(current.disk.used)} / ${formatBytes(current.disk.total)}`} color="text-yellow-400" />
        <StatCard label="Network" value={formatBytes(current.network.bytes_sent)} sub={`Recv: ${formatBytes(current.network.bytes_recv)}`} color="text-purple-400" />
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-white text-sm font-medium mb-4">Usage Over Time</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" stroke="#6b7280" fontSize={11} />
            <YAxis domain={[0, 100]} stroke="#6b7280" fontSize={11} />
            <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
            <Line type="monotone" dataKey="cpu" stroke="#3b82f6" strokeWidth={2} dot={false} name="CPU %" />
            <Line type="monotone" dataKey="memory" stroke="#10b981" strokeWidth={2} dot={false} name="Memory %" />
            <Line type="monotone" dataKey="disk" stroke="#f59e0b" strokeWidth={2} dot={false} name="Disk %" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      <p className="text-gray-500 text-xs mt-1">{sub}</p>
    </div>
  );
}
