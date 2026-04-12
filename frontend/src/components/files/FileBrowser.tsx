"use client";

import { useEffect, useState } from "react";
import { fetchFiles } from "@/lib/api";
import type { Server, DirectoryListing, FileEntry } from "@/types";
import { Folder, File, ArrowUp } from "lucide-react";

interface Props {
  server: Server;
}

export default function FileBrowser({ server }: Props) {
  const [currentPath, setCurrentPath] = useState(server.os === "windows" ? "C:\\" : "/");
  const [listing, setListing] = useState<DirectoryListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDir(path: string) {
    setLoading(true);
    setError("");
    try {
      const data = await fetchFiles(server, path);
      setListing(data);
      setCurrentPath(data.path || path);
    } catch (e) {
      setError("Failed to load directory");
    }
    setLoading(false);
  }

  useEffect(() => { loadDir(currentPath); }, []);

  function navigateUp() {
    const sep = server.os === "windows" ? "\\" : "/";
    const parts = currentPath.split(sep).filter(Boolean);
    parts.pop();
    const parent = server.os === "windows" ? parts.join(sep) + "\\" : "/" + parts.join(sep);
    loadDir(parent || (server.os === "windows" ? "C:\\" : "/"));
  }

  function handleClick(entry: FileEntry) {
    if (entry.type === "directory") {
      const sep = server.os === "windows" ? "\\" : "/";
      loadDir(currentPath.endsWith(sep) ? currentPath + entry.name : currentPath + sep + entry.name);
    }
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
        <button onClick={navigateUp} className="text-gray-400 hover:text-white p-1"><ArrowUp className="w-4 h-4" /></button>
        <span className="text-gray-300 text-sm font-mono">{currentPath}</span>
      </div>
      {error && <p className="text-red-400 text-sm px-4 py-2">{error}</p>}
      {loading ? (
        <p className="text-gray-500 text-center py-8">Loading...</p>
      ) : (
        <div className="divide-y divide-gray-800">
          {listing?.entries.map((entry) => (
            <button key={entry.name} onClick={() => handleClick(entry)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors text-left">
              {entry.type === "directory" ? <Folder className="w-4 h-4 text-blue-400 shrink-0" /> : <File className="w-4 h-4 text-gray-500 shrink-0" />}
              <span className="text-gray-200 text-sm flex-1 truncate">{entry.name}</span>
              <span className="text-gray-500 text-xs">{entry.type === "file" ? formatSize(entry.size) : ""}</span>
            </button>
          ))}
          {listing?.entries.length === 0 && <p className="text-gray-500 text-sm text-center py-8">Empty directory</p>}
        </div>
      )}
    </div>
  );
}
