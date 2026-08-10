"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiGet, ApiError } from "@/lib/api";
import { useSession } from "@/lib/useSession";

interface LinkedInStatus {
  connected: boolean;
  name?: string;
  email?: string;
}

function RedirectNotice() {
  const params = useSearchParams();
  const status = params.get("status");
  const message = params.get("message");

  if (status === "success") {
    return (
      <div className="rounded border border-green-400/50 bg-green-50 p-4 text-sm dark:bg-green-950/30">
        LinkedIn connected successfully.
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="rounded border border-red-400/50 bg-red-50 p-4 text-sm dark:bg-red-950/30">
        Connection failed{message ? `: ${message}` : ""}. Please try again.
      </div>
    );
  }
  return null;
}

export default function ConnectLinkedInPage() {
  const { session } = useSession();
  const [status, setStatus] = useState<LinkedInStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    apiGet<LinkedInStatus>("/api/linkedin/status")
      .then(setStatus)
      .catch((e: ApiError) => setError(e.message));
  }, [session]);

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const { authorize_url } = await apiGet<{ authorize_url: string }>("/api/linkedin/connect");
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start LinkedIn connection");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Connect LinkedIn</h1>

      <Suspense fallback={null}>
        <RedirectNotice />
      </Suspense>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {status?.connected ? (
        <div className="rounded border border-black/10 p-4 text-sm dark:border-white/10">
          <p>
            Connected as <strong>{status.name ?? "your LinkedIn profile"}</strong>
            {status.email ? ` (${status.email})` : ""}.
          </p>
          <button onClick={connect} disabled={busy} className="mt-3 text-sm underline">
            Reconnect / switch account
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-black/70 dark:text-white/70">
            You need to connect your LinkedIn profile before you can publish generated posts. We only request
            permission to read your basic profile and post on your behalf — never to read your existing posts or
            connections.
          </p>
          <button
            onClick={connect}
            disabled={busy || status === null}
            className="w-fit rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {busy ? "Redirecting…" : "Connect LinkedIn"}
          </button>
        </div>
      )}
    </div>
  );
}
