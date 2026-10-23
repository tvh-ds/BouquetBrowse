import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="page-width standard-page empty-state">
      <h1>This bouquet has moved on.</h1>
      <p>
        The listing may have been removed or is not available to this pilot.
      </p>
      <Link className="button primary" href="/search">
        Explore other bouquets
      </Link>
    </main>
  );
}
