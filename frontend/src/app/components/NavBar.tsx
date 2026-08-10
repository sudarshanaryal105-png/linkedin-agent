"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/useSession";
import { supabase } from "@/lib/supabaseClient";

export default function NavBar() {
  const { session, loading } = useSession();
  const router = useRouter();

  async function signOut() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <header className="border-b border-black/10 dark:border-white/10">
      <nav className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <Link href="/" className="font-semibold">
          LinkedIn Content Agent
        </Link>
        <div className="flex items-center gap-4 text-sm">
          {!loading && session && (
            <>
              <Link href="/create">Create</Link>
              <Link href="/history">History</Link>
              <Link href="/connect-linkedin">LinkedIn</Link>
              <button onClick={signOut} className="text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white">
                Sign out
              </button>
            </>
          )}
          {!loading && !session && <Link href="/login">Sign in</Link>}
        </div>
      </nav>
    </header>
  );
}
