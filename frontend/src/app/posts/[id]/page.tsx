"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import type { GeneratedPostOut, GenerationJobOut, PublishResult } from "@/lib/types";
import { useSession } from "@/lib/useSession";

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 80;

export default function PostPreviewPage() {
  const { id } = useParams<{ id: string }>();
  const { session, loading } = useSession();
  const router = useRouter();

  const [post, setPost] = useState<GeneratedPostOut | null>(null);
  const [draftText, setDraftText] = useState("");
  const [draftHashtags, setDraftHashtags] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState<string | null>(null); // action name in flight, for button labels
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    const p = await apiGet<GeneratedPostOut>(`/api/posts/${id}`);
    setPost(p);
    setDraftText(p.post_text);
    setDraftHashtags(p.hashtags.join(", "));
    setDirty(false);
    return p;
  }, [id]);

  useEffect(() => {
    if (!loading && !session) router.push("/login");
  }, [loading, session, router]);

  useEffect(() => {
    if (!session) return;
    apiGet<GeneratedPostOut>(`/api/posts/${id}`)
      .then((p) => {
        setPost(p);
        setDraftText(p.post_text);
        setDraftHashtags(p.hashtags.join(", "));
        setDirty(false);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load post"));
  }, [session, id]);

  async function pollJob(jobId: string): Promise<GenerationJobOut> {
    for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
      const job = await apiGet<GenerationJobOut>(`/api/generation/${jobId}`);
      if (job.status === "SUCCEEDED" || job.status === "FAILED") return job;
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    throw new Error("Regeneration is taking longer than expected.");
  }

  async function saveEdits() {
    if (!post) return;
    setBusy("save");
    setError(null);
    try {
      const hashtags = draftHashtags
        .split(",")
        .map((h) => h.trim().replace(/^#/, ""))
        .filter(Boolean);
      const updated = await apiPatch<GeneratedPostOut>(`/api/posts/${post.id}`, { post_text: draftText, hashtags });
      setPost(updated);
      setDirty(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save changes");
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (!post) return;
    setBusy("approve");
    setError(null);
    try {
      if (dirty) await saveEdits();
      const updated = await apiPost<GeneratedPostOut>(`/api/posts/${post.id}/approve`);
      setPost(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not approve");
    } finally {
      setBusy(null);
    }
  }

  async function regenerate() {
    if (!post) return;
    setBusy("regenerate");
    setError(null);
    try {
      const job = await apiPost<GenerationJobOut>(`/api/posts/${post.id}/regenerate`, { feedback: feedback.trim() || null });
      const finished = await pollJob(job.job_id);
      if (finished.status === "FAILED") {
        setError(finished.error_message ?? "Regeneration failed");
        return;
      }
      await load();
      setFeedback("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not regenerate");
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    if (!post) return;
    setBusy("publish");
    setError(null);
    try {
      const result = await apiPost<PublishResult>("/api/linkedin/publish", { post_id: post.id });
      await load();
      return result;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not publish");
    } finally {
      setBusy(null);
    }
  }

  if (loading || !session || !post) {
    return error ? <p className="text-sm text-red-600">{error}</p> : null;
  }

  const canEdit = post.status !== "PUBLISHING" && post.status !== "PUBLISHED";
  const canApprove = post.status === "DRAFT" || post.status === "EDITED";
  const canPublish = post.status === "APPROVED" || post.status === "FAILED";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Post preview</h1>
        <StatusBadge status={post.status} />
      </div>

      {post.status === "PUBLISHED" && post.linkedin_permalink && (
        <div className="rounded border border-green-400/50 bg-green-50 p-4 text-sm dark:bg-green-950/30">
          Published.{" "}
          <a href={post.linkedin_permalink} target="_blank" rel="noreferrer" className="underline">
            View it on LinkedIn
          </a>
        </div>
      )}

      {post.image_urls.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {post.image_urls.map((url) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={url} src={url} alt="" className="h-32 w-32 rounded border border-black/10 object-cover dark:border-white/10" />
          ))}
        </div>
      )}

      <div>
        <label className="mb-2 block text-sm font-medium">Post text</label>
        <textarea
          value={draftText}
          disabled={!canEdit}
          onChange={(e) => {
            setDraftText(e.target.value);
            setDirty(true);
          }}
          rows={8}
          className="w-full rounded border border-black/15 p-3 disabled:opacity-60 dark:border-white/20"
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium">Hashtags (comma separated)</label>
        <input
          value={draftHashtags}
          disabled={!canEdit}
          onChange={(e) => {
            setDraftHashtags(e.target.value);
            setDirty(true);
          }}
          className="w-full rounded border border-black/15 p-3 disabled:opacity-60 dark:border-white/20"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {canEdit && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={saveEdits}
            disabled={!dirty || busy !== null}
            className="rounded border border-black/15 px-4 py-2 text-sm disabled:opacity-50 dark:border-white/20"
          >
            {busy === "save" ? "Saving…" : "Save changes"}
          </button>

          {canApprove && (
            <button
              onClick={approve}
              disabled={busy !== null}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {busy === "approve" ? "Approving…" : "Approve"}
            </button>
          )}

          {canPublish && (
            <button
              onClick={publish}
              disabled={busy !== null}
              className="rounded bg-green-600 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {busy === "publish" ? "Publishing…" : "Publish to LinkedIn"}
            </button>
          )}
        </div>
      )}

      {canEdit && (
        <div className="rounded border border-black/10 p-4 dark:border-white/10">
          <label className="mb-2 block text-sm font-medium">Not quite right? Ask for a rewrite</label>
          <div className="flex gap-2">
            <input
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="e.g. make it shorter and less formal"
              className="flex-1 rounded border border-black/15 p-2 text-sm dark:border-white/20"
            />
            <button
              onClick={regenerate}
              disabled={busy !== null}
              className="rounded border border-black/15 px-3 py-2 text-sm disabled:opacity-50 dark:border-white/20"
            >
              {busy === "regenerate" ? "Regenerating…" : "Regenerate"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    DRAFT: "bg-gray-200 text-gray-800",
    EDITED: "bg-gray-200 text-gray-800",
    APPROVED: "bg-blue-100 text-blue-800",
    PUBLISHING: "bg-amber-100 text-amber-800",
    PUBLISHED: "bg-green-100 text-green-800",
    FAILED: "bg-red-100 text-red-800",
    CANCELLED: "bg-gray-100 text-gray-500",
  };
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${colors[status] ?? ""}`}>{status}</span>;
}
