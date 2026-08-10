"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiGet, ApiError } from "@/lib/api";
import type { GeneratedPostOut } from "@/lib/types";
import { useSession } from "@/lib/useSession";

export default function HistoryPage() {
  const { session, loading } = useSession();
  const router = useRouter();
  const [posts, setPosts] = useState<GeneratedPostOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !session) router.push("/login");
  }, [loading, session, router]);

  useEffect(() => {
    if (!session) return;
    apiGet<GeneratedPostOut[]>("/api/posts")
      .then(setPosts)
      .catch((e: ApiError) => setError(e.message));
  }, [session]);

  if (loading || !session) return null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">History</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {posts?.length === 0 && <p className="text-sm text-black/60 dark:text-white/60">No posts yet.</p>}
      <ul className="flex flex-col gap-3">
        {posts?.map((post) => (
          <li key={post.id}>
            <Link
              href={`/posts/${post.id}`}
              className="flex items-center justify-between rounded border border-black/10 p-4 hover:bg-black/[0.02] dark:border-white/10 dark:hover:bg-white/[0.02]"
            >
              <div className="min-w-0">
                <p className="truncate text-sm">{post.post_text || "(empty draft)"}</p>
                <p className="mt-1 text-xs text-black/50 dark:text-white/50">{new Date(post.created_at).toLocaleString()}</p>
              </div>
              <span className="ml-4 shrink-0 rounded-full bg-black/5 px-3 py-1 text-xs dark:bg-white/10">{post.status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
