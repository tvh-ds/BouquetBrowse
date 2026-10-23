import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import type { Listing, Seller } from "@/lib/types";
import { BouquetGrid } from "@/components/catalog";
import { Icon } from "@/components/icons";
export default async function SellerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [lang, data] = await Promise.all([
    locale(),
    api<{ seller: Seller; items: Listing[] }>(`/v1/sellers/${id}`),
  ]);
  return (
    <main id="main" className="page-width standard-page">
      <section className="seller-heading">
        <div className="seller-monogram">{data.seller.name.slice(0, 1)}</div>
        <div>
          <h1>{data.seller.name}</h1>
          <p className="location">
            <Icon name="pin" />
            {data.seller.district}, Hà Nội
          </p>
          <p>{data.seller.bio}</p>
          {data.seller.is_demo && (
            <p className="demo-note">
              {lang === "vi"
                ? "Người bán hư cấu trong bản minh họa."
                : "Fictional seller in this demonstration."}
            </p>
          )}
          {data.seller.profile_url && (
            <a
              className="button outline"
              href={data.seller.profile_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {lang === "vi" ? "Trang người bán" : "Original seller profile"}
              <Icon name="external" />
            </a>
          )}
        </div>
      </section>
      <div className="section-heading">
        <h2>{lang === "vi" ? "Những bó hoa từ studio" : "From the studio"}</h2>
        <span>
          {data.items.length} {lang === "vi" ? "bó hoa" : "bouquets"}
        </span>
      </div>
      <BouquetGrid items={data.items} lang={lang} />
    </main>
  );
}
