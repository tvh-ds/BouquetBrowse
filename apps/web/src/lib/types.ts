import type { components } from "./generated-api";
type Schema = components["schemas"];
export type Locale = "vi" | "en";
export type Price = Schema["PriceView"];
export type Seller = Schema["SellerView"] & {
  bio?: string;
  profile_url?: string | null;
  is_demo?: boolean;
};
export type Listing = Schema["ListingView"];
export type Catalog = Schema["CatalogView"];
export type Comparison = Schema["ComparisonView"];
export type Detail = Schema["DetailView"];
export type Facets = Schema["FacetsView"];
export type Session = Schema["SessionView"];
