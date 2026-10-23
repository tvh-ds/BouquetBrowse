import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import type { Detail, Session } from "@/lib/types";
import {
  Studio,
  type StudioData,
  type Overview,
  type Source,
  type Job,
} from "@/components/studio";
export default async function Admin() {
  const [lang, user] = await Promise.all([
    locale(),
    api<Session>("/v1/session"),
  ]);
  if (!["admin", "reviewer"].includes(user.role))
    return (
      <main id="main" className="page-width standard-page empty-state">
        <h1>Reviewer access required.</h1>
        <p>This area is reserved for catalog reviewers and administrators.</p>
      </main>
    );
  const reviews = await api<{ items: Detail[] }>("/v1/admin/reviews");
  const initial: StudioData = {
    overview: null,
    sources: [],
    jobs: [],
    reviews: reviews.items,
  };
  if (user.role === "admin") {
    const [o, s, j] = await Promise.all([
      api<Overview>("/v1/admin/overview"),
      api<{ items: Source[] }>("/v1/admin/sources"),
      api<{ items: Job[] }>("/v1/admin/jobs"),
    ]);
    initial.overview = o;
    initial.sources = s.items;
    initial.jobs = j.items;
  }
  return (
    <main id="main" className="page-width standard-page">
      <div className="page-heading">
        <h1>
          {lang === "vi"
            ? "Chăm chút từng thông tin."
            : "A little care behind every listing."}
        </h1>
        <p>
          {lang === "vi"
            ? "Quản lý nguồn, đối chiếu bằng chứng và giữ bộ sưu tập đáng tin cậy."
            : "Manage sources, inspect evidence, and keep the catalog accountable."}
        </p>
      </div>
      <Studio lang={lang} role={user.role} initial={initial} />
    </main>
  );
}
