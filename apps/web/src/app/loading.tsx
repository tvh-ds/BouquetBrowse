export default function Loading() {
  return (
    <main id="main" className="page-width standard-page" aria-busy="true">
      <div className="loading-note" role="status">
        Đang tìm những bó hoa… / Finding your flowers…
      </div>
      <div className="bouquet-grid">
        {[1, 2, 3, 4].map((n) => (
          <div key={n} className="skeleton-card">
            <div />
            <span />
            <span />
          </div>
        ))}
      </div>
    </main>
  );
}
