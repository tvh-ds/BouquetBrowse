import type { components } from "./generated-api";
export type Change = components["schemas"]["ChangeView"];
export type Digest = components["schemas"]["DigestView"] & {
  coverage: { scheduled?: number; completed?: number; missed?: number };
};
