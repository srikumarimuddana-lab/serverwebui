"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { getServers } from "@/lib/api";
import ServerCard from "@/components/dashboard/ServerCard";
import type { Server } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const [servers, setServers] = useState<Server[]>([]);

  useEffect(() => {
    if (!isAuthenticated()) { router.push("/login"); return; }
    setServers(getServers());
  }, [router]);

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-white">Servers</h1>
          <button onClick={() => router.push("/settings")} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded text-sm">Settings</button>
        </div>
        {servers.length === 0 ? (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg mb-2">No servers configured</p>
            <p className="text-sm">Go to Settings to add your servers</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {servers.map((server) => (
              <ServerCard key={server.id} server={server} onClick={() => router.push(`/server/${server.id}`)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
