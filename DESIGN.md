---
name: BouquetBrowse
description: finding your flowers
colors:
  canvas: "#fbfaf6"
  paper: "#ffffff"
  ink: "#173a2d"
  muted: "#59675e"
  blush: "#e7c4c2"
  soft: "#eaf0e6"
  line: "#dedfd5"
  error: "#9c332d"
typography:
  display:
    fontFamily: '"Bodoni Moda", Georgia, serif'
    fontSize: "clamp(36px, 4.7vw, 64px)"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-0.035em"
  body:
    fontFamily: '"Be Vietnam Pro", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
  metadata-mobile:
    fontFamily: '"Be Vietnam Pro", sans-serif'
    fontSize: "12px"
    lineHeight: 1.55
rounded:
  badge: "4px"
  button: "9px"
  search: "10px"
  card: "12px"
  detail: "14px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.button}"
    padding: "11px 19px"
  button-secondary:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
  demo-badge:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.badge}"
    padding: "2px 6px"
---

# Design System: BouquetBrowse

## Overview

**Creative North Star: "A florist's discovery journal"**

Preserve the approved quiet botanical direction: warm ivory, deep forest text, restrained blush, editorial serif headings and practical Vietnamese typography. Bouquet photography supplies most of the color; the interface supports discovery and evidence reading with useful catalog density.

This is a code-led record of the built system in apps/web/src, refreshed from its CSS and components. No approved visual comp exists. The approved product brief and technical blueprint govern implementation; this refresh records the incumbent system without replacing its identity. The original tagline remains **finding your flowers**. Surface composition and review evidence live in [the discovery surface brief](docs/DISCOVERY-SURFACE.md).

**Key Characteristics:**

- Photo-forward catalog with softly rounded image frames.
- Forest controls, ivory canvas and fine neutral rules.
- Expressive headings paired with compact evidence labels.
- Shared visual language for shopping, comparisons and catalog operations.

## Colors

The frontmatter records the actual root CSS palette. Ink carries headings, body text and primary actions; muted supports secondary copy. Canvas surrounds paper search fields and forms. Soft green supports secondary/selected controls and benchmark panels. Blush appears in selection highlighting. Fine line borders divide content without heavy framing; error marks form failures.

**The Photography Rule.** Let bouquet images carry the varied color; preserve the restrained botanical interface around them.

## Typography

Display uses self-hosted **Bodoni Moda** (Georgia fallback), loaded through Fontsource at weight 500 with an italic face. Body and controls use self-hosted **Be Vietnam Pro**, with weights 400, 500, 600 and 700 loaded and Vietnamese glyph support. Fraunces is not the built display font.

The frontmatter display style is the default h1. Default h2 scales from 27–38px; h3 uses the sans face at 17px/500. The discovery hero has its own larger heading (45–72px fluid, 52px below 600px). Body becomes 13px below 600px. Paragraphs generally cap at 72ch. Prices use tabular numerals and stronger weight.

At widths up to 640px, essential catalog metadata—seller caption, attributes, price provenance and posted date—uses the frontmatter mobile metadata style. Fictional-demo badges are 12px at every width. Other dense evidence/admin labels retain their component-specific sizes; this is not a universal 12px minimum throughout the application.

## Layout

The main container caps at 1320px with 56px side padding. Padding steps to 32px at 1100px, 24px at 800px and 20px at 600px. Standard pages start with 44px top and 72px bottom space, reducing to 29px/40px below 600px.

The discovery hero is a two-column text/photo grid (1.25fr/1fr); below 600px it becomes one column and hides the featured photo. Catalog grids use four columns, three below 800px and two below 600px. Desktop navigation is sticky; below 800px the header returns to document flow and navigation wraps onto a second row. At small widths navigation can scroll horizontally.

Catalog and detail photographs use 4:5 frames. The hero uses 1:1.06 with an arched top, changing to 3:4 below 800px before hiding on phones. Comparison photos use 4:4.5. Comparison columns use an auto-fit grid with a 200px minimum and become two columns below 600px; they do not turn into stacked comparison tables. Detail and evidence grids become single-column below 600px. Operational tables retain horizontal overflow.

Research operations extends the existing Studio with a workspace selector capped at 28rem and a heading paired with an outlined refresh action. Summary definitions use three columns; independent annotation fields use two. At 640px and below, headings, action rows, summaries and annotation columns stack; inspector padding reduces from 1.5rem to 1rem. Action groups wrap. Long evidence identifiers and source text wrap within their containers; proof tables retain local horizontal scrolling. Evidence images use contained 4:5 frames so inspection preserves the full source image.

## Elevation & Depth

Cards are flat at rest; borders and soft surface tones provide structure. The fixed comparison tray is the deliberate lifted surface, using a shadow of 0 6px 34px #173a2d2b. The native filter dialog dims the page with a forest backdrop (rgb(23 58 45 / 35%)).

Image hover scales gently (1.025 over 0.45s); the desktop hero rotates 1.5 degrees and straightens on hover. Buttons transition background and color over 0.15s. Reduced-motion settings disable transitions/animations, restore automatic scrolling and remove the hero rotation.

## Shapes

The frontmatter captures recurring radii: badges, buttons, search fields, image cards and detail frames. Mobile catalog images use 10px corners. Circular icon actions contrast with those frames. The hero has a botanical arch (120px top corners, 12px bottom corners; 80px/10px below 800px). The mobile filter sheet has 18px upper corners.

## Components

**Buttons and focus.** Primary buttons use forest ink on ivory; secondary buttons use soft green. Outlined buttons have a muted green border and soft-green hover fill. The base button minimum height is 44px. The card comparison button, card detail arrow and comparison-tray clear button explicitly measure at least 44×44px at all widths. Other component overrides exist, so do not infer that every action already meets that size. Keyboard focus uses a visible 3px green outline with a 4px offset.

**Search and filters.** Search is a white, finely bordered rounded field with a separate submit button. Filters use server-backed GET forms and URL state. Above 640px filters remain inline. At 640px and below a full-width trigger opens a native modal dialog as a bottom sheet capped at 85dvh; native focus containment and Escape dismissal accompany explicit close and backdrop dismissal. Legacy details-drawer styles do not describe the active filter component.

**Bouquet cards and price labels.** Photographs precede seller, title, configuration, advertised/unknown price and posted date. Show the fictional-demo badge beside each price block only when that listing's is_demo flag is true. Shared price labels carry this treatment across catalog, details and comparisons. The global research strip provides session context; it does not replace per-item evidence labels.

**Comparison.** Selection persists in local storage with a four-bouquet limit and a fixed bottom tray. A selected icon uses forest fill and a check. Removing an item on the comparison route updates stored selection and the URL, removing the corresponding rendered column. Clearing there navigates to the empty comparison. Benchmark panels remain visually distinct from manually selected alternatives, with their own conditional fictional-statistics notice.

**Catalog operations.** Admin tabs share forest selection, rounded forms and neutral rules. Summaries wrap, review forms become one column on phones and dense tables scroll horizontally. Preserve the same typography and palette while allowing task-appropriate density.

**Research controls and evidence.** The admin-only Research & operations tab offers six workspaces: health, conversations, flower taxonomy, canonical configurations, evaluation and release proofs. Fine ruled rows lead into lightly bordered inspectors; native selects, textareas, multi-selects and disclosures keep evidence close to its next action. Research buttons and ordinary fields have a 44px minimum height; checkboxes use a smaller native control within a 44px label row. All retain the shared focus outline, botanical palette and inherited reduced-motion behavior. Loading and successful actions use status messages; failures use alerts, and busy actions disable their submit buttons. Empty, unknown, stale and unconfigured states carry explicit copy rather than implied success.

**Research workflow continuity.** All six research panels remain mounted while the workspace selector changes, preserving local selection and unsaved forms during those changes. Adding an associated offer image opens the evaluation draft, avoids duplicate media and preserves malformed JSON with a correction alert. Workspace refresh updates evidence; health refreshes every 30 seconds while its workspace is active and the document is visible. Leaving the outer Research tab unmounts its state, so this is not durable draft storage. Taxonomy decisions, seller-scoped canonical links, independent annotations and proof attestations remain distinct actions with adjacent reasons or evidence. Full identifiers, relationships and report/configuration hashes use native disclosures rather than taking over the first viewport.

**Seller summary.** Seller pages optionally show the localized observed summary, flower types and styles beside the existing identity and seller-stated details. Omit empty observation lists and retain the conditional fictional-seller notice. This extension was reviewed in code only; the research finish capture set does not establish its visual layout.

## Do's and Don'ts

- **Do** preserve the pinned quiet botanical identity and original tagline.
- **Do** use the actual self-hosted font pair and Vietnamese typography.
- **Do** retain 4:5 catalog imagery, two-column phone results, visible focus and reduced-motion behavior.
- **Do** keep the named card/tray actions at 44px and essential phone catalog metadata at 12px.
- **Do** condition fictional evidence labels on the underlying record, adjacent to its price or statistics.
- **Do** distinguish staged, synthetic, under-sampled, unsupported and approved research evidence; controls must reflect the available capability and proof state.
- **Don't** replace the code-led contract with an invented approved comp.
- **Don't** visually conflate recommendations with qualified price benchmarks or imply that review verifies inventory.
- **Don't** generalize scoped review evidence into a whole-application accessibility or visual certification.
