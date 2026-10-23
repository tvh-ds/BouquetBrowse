import Link from "next/link";
import Image from "next/image";
import type { Facets, Listing, Locale } from "@/lib/types";
import { date, label, money, words } from "@/lib/i18n";
import { CompareButton } from "./controls";
import { Icon } from "./icons";
import { FilterPanel } from "./filter-panel";
export function BouquetImage({
  listing,
  priority = false,
}: {
  listing: Listing;
  priority?: boolean;
}) {
  return listing.image_path ? (
    <Image
      src={listing.image_path}
      alt={`${label(listing.color, "en")} ${label(listing.primary_flower, "en")} ${label(listing.arrangement, "en")}`}
      fill
      sizes="(max-width:640px) 50vw, (max-width:1024px) 33vw, 25vw"
      priority={priority}
      unoptimized={listing.image_path.startsWith("/api/")}
      className="bouquet-image"
    />
  ) : (
    <div className="image-empty">
      <Icon name="leaf" />
      <span>Photo unavailable</span>
    </div>
  );
}
export function PriceLabel({
  listing,
  lang,
}: {
  listing: Listing;
  lang: Locale;
}) {
  const p = listing.price;
  return (
    <div className="price-block">
      {listing.is_demo && (
        <span className="demo-badge">
          {lang === "vi" ? "Minh họa hư cấu" : "Fictional demo"}
        </span>
      )}
      <span className="price-caption">
        {p ? words[lang].advertised : words[lang].unknownPrice}
      </span>
      {p && (
        <span className="price">
          {p.kind === "from" ? (lang === "vi" ? "Từ " : "From ") : ""}
          {money(p.amount_min, p.currency)}
          {p.kind === "range" &&
          p.amount_max !== null &&
          p.amount_max !== p.amount_min
            ? ` – ${money(p.amount_max, p.currency)}`
            : ""}
        </span>
      )}
    </div>
  );
}
export function BouquetCard({
  listing,
  lang,
  priority = false,
}: {
  listing: Listing;
  lang: Locale;
  priority?: boolean;
}) {
  const title =
    lang === "en" && typeof listing.attributes.title_en === "string"
      ? listing.attributes.title_en
      : listing.title;
  return (
    <article className="bouquet-card">
      <div className="card-photo">
        <Link href={`/bouquets/${listing.id}`} aria-label={title}>
          <BouquetImage listing={listing} priority={priority} />
        </Link>
        <CompareButton id={listing.id} lang={lang} compact />
        <span className="photo-label">
          {label(listing.primary_flower, lang)}
        </span>
      </div>
      <div className="card-body">
        <Link className="seller-caption" href={`/sellers/${listing.seller.id}`}>
          {listing.seller.name}
          <span> · {listing.seller.district}</span>
        </Link>
        <h3>
          <Link href={`/bouquets/${listing.id}`}>{title}</Link>
        </h3>
        <div className="card-attributes">
          {listing.stem_count
            ? `${listing.stem_count} ${words[lang].stems}`
            : label(listing.arrangement, lang)}
          <span>·</span>
          {label(listing.color, lang)}
        </div>
        <div className="card-price-row">
          <PriceLabel listing={listing} lang={lang} />
          <Link
            href={`/bouquets/${listing.id}`}
            className="card-arrow"
            aria-label={lang === "vi" ? `Xem ${title}` : `View ${title}`}
          >
            <Icon name="arrow" />
          </Link>
        </div>
        {listing.published_at && (
          <span className="card-date">
            {lang === "vi" ? "Đăng" : "Posted"}{" "}
            {date(listing.published_at, lang)}
          </span>
        )}
      </div>
    </article>
  );
}
export function BouquetGrid({
  items,
  lang,
}: {
  items: Listing[];
  lang: Locale;
}) {
  return items.length ? (
    <div className="bouquet-grid">
      {items.map((listing, index) => (
        <BouquetCard
          key={listing.id}
          listing={listing}
          lang={lang}
          priority={index < 4}
        />
      ))}
    </div>
  ) : (
    <div className="empty-state">
      <Icon name="leaf" />
      <h2>{words[lang].noResults}</h2>
      <p>{words[lang].noResultsHint}</p>
      <Link className="button outline" href="/search">
        {words[lang].clear}
      </Link>
    </div>
  );
}
export function SearchBox({
  q = "",
  lang,
  large = false,
}: {
  q?: string;
  lang: Locale;
  large?: boolean;
}) {
  return (
    <form action="/search" className={`search-box ${large ? "large" : ""}`}>
      <Icon name="search" />
      <label
        className="sr-only"
        htmlFor={large ? "hero-search" : "catalog-search"}
      >
        {words[lang].search}
      </label>
      <input
        id={large ? "hero-search" : "catalog-search"}
        type="search"
        name="q"
        placeholder={words[lang].search}
        defaultValue={q}
        maxLength={200}
      />
      <button className="button primary" type="submit">
        {words[lang].searchButton}
        <Icon name="arrow" />
      </button>
    </form>
  );
}
export function Filters({
  facets,
  values,
  lang,
}: {
  facets: Facets;
  values: Record<string, string | undefined>;
  lang: Locale;
}) {
  const w = words[lang];
  return (
    <FilterPanel title={w.filters} close={lang === "vi" ? "Đóng" : "Close"}>
      <form action="/search" className="filters">
        <input type="hidden" name="q" value={values.q || ""} />
        {(
          [
            ["flower", w.flower, facets.flowers],
            ["color", w.color, facets.colors],
            ["district", w.district, facets.districts],
            [
              "arrangement",
              lang === "vi" ? "Kiểu dáng" : "Arrangement",
              facets.arrangements,
            ],
            [
              "occasion",
              lang === "vi" ? "Dịp tặng" : "Occasion",
              facets.occasions,
            ],
          ] as [string, string, string[]][]
        ).map(([key, name, options]) => (
          <label key={key}>
            <span>{name}</span>
            <select name={key} defaultValue={values[key] || ""}>
              <option value="">{w.all}</option>
              {options.map((value) => (
                <option key={value} value={value}>
                  {label(value, lang)}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          <span>
            {lang === "vi" ? "Giao hàng được quảng cáo" : "Advertised delivery"}
          </span>
          <select name="delivery" defaultValue={values.delivery || ""}>
            <option value="">{w.all}</option>
            <option value="true">{lang === "vi" ? "Có" : "Offered"}</option>
            <option value="false">
              {lang === "vi" ? "Không" : "Not offered"}
            </option>
          </select>
        </label>
        <label>
          <span>{w.budget}</span>
          <select name="max_price" defaultValue={values.max_price || ""}>
            <option value="">{w.all}</option>
            {[400000, 600000, 800000, 1000000].map((value) => (
              <option key={value} value={value}>
                ≤ {money(value)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{w.sort}</span>
          <select name="sort" defaultValue={values.sort || "recommended"}>
            <option value="recommended">{w.recommended}</option>
            <option value="price-asc">{w.priceAsc}</option>
            <option value="price-desc">{w.priceDesc}</option>
            <option value="freshest">{w.freshest}</option>
          </select>
        </label>
        <button className="button primary filter-apply" type="submit">
          {w.apply}
        </button>
      </form>
    </FilterPanel>
  );
}
