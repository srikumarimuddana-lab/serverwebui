"use client";

import { useState } from "react";
import { fetchLogs } from "@/lib/api";
import type { Server, LogResponse } from "@/types";

interface Props { server: Server; }

export default function LogViewer({ server }: Props) {
  const [logPath, setLogPath] = useState("");
  const [logData, setLogData] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadLog() {
    if (!logPath.trim()) return;
    setLoading(true); setError("");
    try { const data = await fetchLogs(server, logPath); setLogData(data); }
    catch { setError("Failed to load log file"); }
    setLoading(false);
  }

  async function loadMore() {
    if (!logData) return;
    setLoading(true);
    try {
      const data = await fetchLogs(server, logPath, logData.offset + logData.limit);
      setLogData((prev) => prev ? { ...data, lines: [...prev.lines, ...data.lines] } : data);
    } catch { setError("Failed to load more"); }
    setLoading(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input type="text" value={logPath} onChange={(e) => setLogPath(e.target.value)}
          placeholder={server.os === "windows" ? "C:\\path\\to\\log.txt" : "/var/log/syslog"}
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500 font-mono" />
        <button onClick={loadLog} disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm disabled:opacity-50">Load</button>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {logData && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg">
          <div className="px-4 py-2 border-b border-gray-800 flex justify-between items-center">
            <span className="text-gray-400 text-xs font-mono">{logData.path}</span>
            <span className="text-gray-500 text-xs">{logData.total_lines} total lines</span>
          </div>
          <pre className="p-4 text-sm text-gray-300 font-mono overflow-auto max-h-[600px] leading-relaxed">
            {logData.lines.map((line, i) => (
              <div key={i} className="hover:bg-gray-800">
                <span className="text-gray-600 select-none mr-3">{logData.offset + i + 1}</span>{line}
              </div>
            ))}
          </pre>
          {logData.offset + logData.lines.length < logData.total_lines && (
            <div className="px-4 py-2 border-t border-gray-800">
              <button onClick={loadMore} disabled={loading} className="text-blue-400 text-sm hover:underline">Load more...</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
