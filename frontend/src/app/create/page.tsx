"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiPost, apiUpload, ApiError } from "@/lib/api";
import type { GenerationJobOut, UploadedImageOut } from "@/lib/types";
import { useSession } from "@/lib/useSession";

const MAX_IMAGES = 6;
const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 80; // ~2 minutes

interface PreviewImage {
  file: File;
  url: string;
}

export default function CreatePostPage() {
  const { session, loading } = useSession();
  const router = useRouter();

  const [images, setImages] = useState<PreviewImage[]>([]);
  const [promptText, setPromptText] = useState("");
  const [optionalContext, setOptionalContext] = useState("");
  const [phase, setPhase] = useState<"idle" | "uploading" | "generating" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!loading && !session) router.push("/login");
  }, [loading, session, router]);

  useEffect(() => {
    return () => images.forEach((img) => URL.revokeObjectURL(img.url));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addFiles(fileList: FileList | null) {
    if (!fileList) return;
    const next = [...images];
    for (const file of Array.from(fileList)) {
      if (next.length >= MAX_IMAGES) break;
      next.push({ file, url: URL.createObjectURL(file) });
    }
    setImages(next);
  }

  function removeImage(index: number) {
    setImages((prev) => {
      const copy = [...prev];
      const [removed] = copy.splice(index, 1);
      if (removed) URL.revokeObjectURL(removed.url);
      return copy;
    });
  }

  async function pollJob(jobId: string): Promise<GenerationJobOut> {
    for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
      const job = await apiGet<GenerationJobOut>(`/api/generation/${jobId}`);
      if (job.status === "SUCCEEDED" || job.status === "FAILED") return job;
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    throw new Error("Generation is taking longer than expected. Check History shortly.");
  }

  async function generate() {
    if (images.length === 0) {
      setError("Add at least one photo.");
      return;
    }
    if (!promptText.trim()) {
      setError("Describe what you want the post to say.");
      return;
    }

    setError(null);
    try {
      setPhase("uploading");
      const uploaded = await apiUpload<UploadedImageOut[]>(
        "/api/upload",
        images.map((img) => img.file)
      );

      setPhase("generating");
      const job = await apiPost<GenerationJobOut>("/api/generate", {
        prompt_text: promptText,
        optional_context: optionalContext.trim() || null,
        image_ids: uploaded.map((u) => u.id),
      });

      const finished = await pollJob(job.job_id);
      if (finished.status === "FAILED") {
        setError(finished.error_message ?? "Generation failed. Try again.");
        setPhase("error");
        return;
      }
      router.push(`/posts/${finished.generated_post_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Something went wrong.");
      setPhase("error");
    }
  }

  if (loading || !session) return null;
  const busy = phase === "uploading" || phase === "generating";

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Create a post</h1>

      <div>
        <label className="mb-2 block text-sm font-medium">Photos</label>
        <div className="flex flex-wrap gap-3">
          {images.map((img, i) => (
            <div key={img.url} className="relative h-24 w-24 overflow-hidden rounded border border-black/10 dark:border-white/10">
              {/* eslint-disable-next-line @next/next/no-img-element -- local blob: preview URL, next/image can't optimize it */}
              <img src={img.url} alt="" className="h-full w-full object-cover" />
              <button
                onClick={() => removeImage(i)}
                className="absolute right-0 top-0 bg-black/60 px-1.5 text-xs text-white"
                aria-label="Remove image"
              >
                ×
              </button>
            </div>
          ))}
          {images.length < MAX_IMAGES && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex h-24 w-24 items-center justify-center rounded border border-dashed border-black/25 text-2xl text-black/40 dark:border-white/25 dark:text-white/40"
            >
              +
            </button>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/gif"
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium">What do you want the post to say?</label>
        <textarea
          value={promptText}
          onChange={(e) => setPromptText(e.target.value)}
          rows={4}
          placeholder="e.g. I completed this certification — create a professional but natural announcement post."
          className="w-full rounded border border-black/15 p-3 dark:border-white/20"
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium">Extra context (optional)</label>
        <textarea
          value={optionalContext}
          onChange={(e) => setOptionalContext(e.target.value)}
          rows={2}
          placeholder="Anything the photos don't show — e.g. the course took 3 months, or the event name."
          className="w-full rounded border border-black/15 p-3 dark:border-white/20"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        onClick={generate}
        disabled={busy}
        className="w-fit rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {phase === "uploading" && "Uploading photos…"}
        {phase === "generating" && "Generating draft…"}
        {(phase === "idle" || phase === "error") && "Generate"}
      </button>
    </div>
  );
}
