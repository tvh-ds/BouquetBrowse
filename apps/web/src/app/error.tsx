"use client";
import Link from "next/link";
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main id="main" className="page-width standard-page empty-state">
      <h1>A little pause in the garden.</h1>
      <p>
        {error.message.includes("access")
          ? "Your account does not have access to this page."
          : "The catalog could not be loaded. Check the API service and try again."}
      </p>
      <button className="button primary" onClick={reset}>
        Try again
      </button>
      <Link className="underlined-link" href="/">
        Return to discovery
      </Link>
    </main>
  );
}
