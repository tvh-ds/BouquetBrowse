import Link from "next/link";
import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import { words } from "@/lib/i18n";
import type { Catalog, Facets } from "@/lib/types";
import { BouquetGrid, Filters, SearchBox } from "@/components/catalog";
export default async function Search({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const values: Record<string, string | undefined> = {};
  for (const key of [
    "q",
    "flower",
    "color",
    "district",
    "arrangement",
    "occasion",
    "delivery",
    "max_price",
    "min_price",
    "sort",
    "cursor",
  ])
    if (typeof raw[key] === "string") values[key] = raw[key];
  const query = new URLSearchParams(
    Object.entries(values).filter(
      (entry): entry is [string, string] => entry[1] !== undefined,
    ),
  );
  const [lang, result, facets] = await Promise.all([
    locale(),
    api<Catalog>(`/v1/catalog?${query}`),
    api<Facets>("/v1/catalog/facets"),
  ]);
  const next = new URLSearchParams(query);
  if (result.next_cursor) next.set("cursor", result.next_cursor);
  return (
    <main id="main" className="page-width standard-page">
      <div className="page-heading">
        <h1>
          {values.q
            ? `${words[lang].discover}: “${values.q}”`
            : words[lang].discover}
        </h1>
        <p>
          {lang === "vi"
            ? "Tìm một bó hoa đúng với điều bạn muốn gửi gắm."
            : "Find the bouquet that says what you have in mind."}
        </p>
      </div>
      <SearchBox q={values.q} lang={lang} />
      <Filters facets={facets} values={values} lang={lang} />
      <div className="results-note">
        <span>
          {result.total} {words[lang].flowersFound}
        </span>
        {Object.keys(values).length > 0 && (
          <Link href="/search">{words[lang].clear}</Link>
        )}
      </div>
      <BouquetGrid items={result.items} lang={lang} />
      {result.next_cursor && (
        <div className="catalog-bottom">
          <Link className="button outline" href={`/search?${next}`}>
            {lang === "vi" ? "Trang tiếp" : "Next page"}
          </Link>
        </div>
      )}
    </main>
  );
}
