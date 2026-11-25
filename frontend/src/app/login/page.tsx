"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const { error } =
      mode === "sign-in"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    setBusy(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.push("/");
  }

  async function signInWithLinkedIn() {
    setError(null);
    setBusy(true);
    // Redirects the whole page to LinkedIn; on success LinkedIn sends the browser back to
    // Supabase's own callback, which sets the session and lands here already signed in.
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "linkedin_oidc",
      options: { redirectTo: `${window.location.origin}/` },
    });
    if (error) {
      setError(error.message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-xl font-semibold">{mode === "sign-in" ? "Sign in" : "Create an account"}</h1>

      <button
        onClick={signInWithLinkedIn}
        disabled={busy}
        className="mb-4 flex w-full items-center justify-center gap-2 rounded border border-black/15 px-3 py-2 text-sm font-medium disabled:opacity-50 dark:border-white/20"
      >
        <LinkedInIcon />
        Continue with LinkedIn
      </button>

      <div className="mb-4 flex items-center gap-3 text-xs text-black/40 dark:text-white/40">
        <div className="h-px flex-1 bg-black/10 dark:bg-white/10" />
        or
        <div className="h-px flex-1 bg-black/10 dark:bg-white/10" />
      </div>

      <form onSubmit={submit} className="flex flex-col gap-3">
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-black/15 px-3 py-2 dark:border-white/20"
        />
        <input
          type="password"
          required
          minLength={6}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-black/15 px-3 py-2 dark:border-white/20"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Please wait…" : mode === "sign-in" ? "Sign in" : "Sign up"}
        </button>
      </form>
      <button
        className="mt-4 text-sm text-black/60 underline dark:text-white/60"
        onClick={() => setMode(mode === "sign-in" ? "sign-up" : "sign-in")}
      >
        {mode === "sign-in" ? "Need an account? Sign up" : "Already have an account? Sign in"}
      </button>
    </div>
  );
}

function LinkedInIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="#0A66C2" aria-hidden="true">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.124 2.062 2.062 0 0 1 0 4.124zM7.114 20.452H3.558V9h3.556v11.452z" />
    </svg>
  );
}
