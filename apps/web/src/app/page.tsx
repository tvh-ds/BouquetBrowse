import Link from "next/link";
import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import { words } from "@/lib/i18n";
import type { Catalog, Facets } from "@/lib/types";
import {
  BouquetGrid,
  BouquetImage,
  Filters,
  SearchBox,
} from "@/components/catalog";
import { Icon } from "@/components/icons";
export default async function Home() {
  const lang = await locale();
  const w = words[lang];
  const [catalog, facets] = await Promise.all([
    api<Catalog>("/v1/catalog?limit=12"),
    api<Facets>("/v1/catalog/facets"),
  ]);
  const featured =
    catalog.items.find((item) => item.color === "pink") || catalog.items[0];
  return (
    <main id="main">
      <section className="hero page-width">
        <div className="hero-copy">
          <h1>
            {w.hero.split("\n")[0]}
            <br />
            <em>{w.hero.split("\n")[1]}</em>
          </h1>
          <p>{w.intro}</p>
          <SearchBox lang={lang} large />
          <div className="quick-searches">
            <span>{lang === "vi" ? "Thử tìm" : "Try"}</span>
            <Link href="/search?flower=rose">
              {lang === "vi" ? "Hoa hồng" : "Roses"}
            </Link>
            <Link href="/search?max_price=600000">
              {lang === "vi" ? "Dưới 600k" : "Under 600k"}
            </Link>
            <Link href="/search?occasion=birthday">
              {lang === "vi" ? "Quà sinh nhật" : "Birthday flowers"}
            </Link>
          </div>
        </div>
        {featured && (
          <Link className="hero-feature" href={`/bouquets/${featured.id}`}>
            <div className="hero-photo">
              <BouquetImage listing={featured} priority />
            </div>
            <div className="hero-photo-caption">
              <span>{w.featured}</span>
              <span>
                {featured.seller.name}
                <Icon name="arrow" />
              </span>
            </div>
          </Link>
        )}
      </section>
      <section className="catalog-section page-width">
        <div className="section-heading">
          <div>
            <h2>{w.catalog}</h2>
            <p>{w.catalogIntro}</p>
          </div>
          <Link href="/search" className="underlined-link">
            {w.browse}
            <Icon name="arrow" />
          </Link>
        </div>
        <Filters facets={facets} values={{}} lang={lang} />
        <div className="results-note">
          <span>
            {catalog.total} {w.flowersFound}
          </span>
          <span>
            {lang === "vi"
              ? "Giá từ quảng cáo · Tình trạng hàng cần xác nhận"
              : "Advertised prices · Availability requires confirmation"}
          </span>
        </div>
        <BouquetGrid items={catalog.items} lang={lang} />
        <div className="catalog-bottom">
          <Link className="button outline" href="/search">
            {w.browse}
            <Icon name="arrow" />
          </Link>
        </div>
      </section>
    </main>
  );
}
