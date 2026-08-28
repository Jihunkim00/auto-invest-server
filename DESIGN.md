# Auto Invest UI Design Notes

## Direction

Auto Invest uses a Korean-first dark fintech interface. The visual language is
calm, information-dense, and operational: important state is always explicit,
while decorative treatment stays restrained so users can focus on account,
portfolio, and decision status.

The system is inspired by the public Revolut design notes for its use of dark
surface layering, hairline dividers, compact spacing, rounded controls, and
responsive grids. It is an adaptation for this product, not a copy of
proprietary assets or typography.

## Tokens

- Canvas: #090B0D
- Surface: #111518
- Elevated surface: #171C20
- Hairline: white at 12% opacity
- Accent: #9AA8FF
- Positive: #48D597
- Warning: #FFB454
- Danger: #FF6B78
- Card radius: 20px
- Input radius: 12px
- Page padding: 16px
- Spacing rhythm: 4 / 8 / 16 / 24 / 32px

Korean-friendly system fallbacks are used instead of a proprietary font:
Noto Sans KR, Malgun Gothic, and Arial.

## Component behavior

- Cards use surface contrast and a thin border; no gradients or heavy shadows.
- Inputs and buttons keep a clear 44–48px touch target.
- Chips and status badges are compact pills with a single semantic accent.
- Loading, connected, and error states use distinct copy and iconography.
- Portfolio values stay hidden until the account snapshot is loaded; zero is
  never used as a loading placeholder.
- AI chat is analysis-only in this surface. The UI states that it cannot submit
  orders, and any backend-provided safety state remains visible.

## Responsive rules

- At 1440px, content is centered with a maximum width and cards can form a
  balanced multi-column layout.
- At 1024px, cards reduce to two columns where the content remains readable.
- At 768px, controls wrap and section actions may move below their headings.
- At 430px, pages use one column, Korean labels wrap naturally, and no
  horizontal scrolling is required for primary actions.

## Content rules

- User-facing navigation and primary dashboard labels are Korean by default.
- Broker names use Korean display names: 한국투자증권 and 알파카.
- Dates sent to the API remain strict yyyy-MM-dd strings.
- Trading, scheduling, sizing, risk, and order semantics belong to the backend;
  this UI layer only presents their current state.
