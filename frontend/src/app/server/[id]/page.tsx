"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { getServers } from "@/lib/api";
import type { Server } from "@/types";
import { ArrowLeft, TerminalSquare, FolderOpen, Activity, FileText, Settings } from "lucide-react";
import dynamic from "next/dynamic";

const TerminalPanel = dynamic(() => import("@/components/terminal/TerminalPanel"), { ssr: false });
const StatsPanel = dynamic(() => import("@/components/stats/StatsPanel"), { ssr: false });
import FileBrowser from "@/components/files/FileBrowser";
import LogViewer from "@/components/logs/LogViewer";
import ServiceManager from "@/components/services/ServiceManager";

type Tab = "terminal" | "files" | "stats" | "logs" | "services";

const tabs: { id: Tab; label: string; icon: typeof TerminalSquare }[] = [
  { id: "terminal", label: "Terminal", icon: TerminalSquare },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "stats", label: "Stats", icon: Activity },
  { id: "logs", label: "Logs", icon: FileText },
  { id: "services", label: "Services", icon: Settings },
];

export default function ServerPage() {
  const params = useParams();
  const router = useRouter();
  const [server, setServer] = useState<Server | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("terminal");

  useEffect(() => {
    if (!isAuthenticated()) { router.push("/login"); return; }
    const servers = getServers();
    const found = servers.find((s) => s.id === Number(params.id));
    if (found) setServer(found);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  if (!server) return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">Loading...</div>;

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <div className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-bold text-white">{server.hostname}</h1>
          <span className="text-gray-500 text-sm">{server.ip_address}</span>
          <span className="text-gray-600 text-xs capitalize">{server.os}</span>
        </div>
      </div>
      <div className="border-b border-gray-800 px-6">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id ? "border-blue-500 text-blue-400" : "border-transparent text-gray-400 hover:text-white"
              }`}>
              <tab.icon className="w-4 h-4" />{tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 p-6">
        {activeTab === "terminal" && <TerminalPanel server={server} />}
        {activeTab === "files" && <FileBrowser server={server} />}
        {activeTab === "stats" && <StatsPanel server={server} />}
        {activeTab === "logs" && <LogViewer server={server} />}
        {activeTab === "services" && <ServiceManager server={server} />}
      </div>
    </div>
  );
}
