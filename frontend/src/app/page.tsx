"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/useSession";
import { apiGet, ApiError } from "@/lib/api";

interface LinkedInStatus {
  connected: boolean;
  name?: string;
}

export default function HomePage() {
  const { session, loading } = useSession();
  const router = useRouter();
  const [status, setStatus] = useState<LinkedInStatus | null>(null);

  useEffect(() => {
    if (!loading && !session) router.push("/login");
  }, [loading, session, router]);

  useEffect(() => {
    if (!session) return;
    apiGet<LinkedInStatus>("/api/linkedin/status")
      .then(setStatus)
      .catch((e: ApiError) => console.error(e));
  }, [session]);

  if (loading || !session) return null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Welcome back</h1>

      {status && !status.connected && (
        <div className="rounded border border-amber-400/50 bg-amber-50 p-4 text-sm dark:bg-amber-950/30">
          Your LinkedIn account isn&apos;t connected yet.{" "}
          <Link href="/connect-linkedin" className="underline">
            Connect it
          </Link>{" "}
          before you can publish.
        </div>
      )}
      {status?.connected && (
        <div className="rounded border border-green-400/50 bg-green-50 p-4 text-sm dark:bg-green-950/30">
          Connected to LinkedIn as {status.name ?? "your profile"}.
        </div>
      )}

      <div className="flex gap-4">
        <Link href="/create" className="rounded bg-blue-600 px-4 py-2 text-white">
          Create a post
        </Link>
        <Link href="/history" className="rounded border border-black/15 px-4 py-2 dark:border-white/20">
          View history
        </Link>
      </div>
    </div>
  );
}
