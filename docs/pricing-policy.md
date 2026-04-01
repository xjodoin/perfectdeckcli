# Pricing Policy

This document defines the pricing policy for `perfectdeckcli` when generating
regional prices for one-time products such as credit packs.

## Decision Order

When these goals conflict, apply them in this order:

1. Preserve the value ladder.
2. Respect valid localized store price points.
3. Prefer psychological endings such as `.99`.

In short:

`value ladder > localized store point > .99 ending`

## Core Rules

### 1. Never round below the computed local target

Generated prices must snap upward to the next valid store price point.

Why:
- Rounding down breaks the intended PPP/exchange-rate target.
- Rounding down makes bundle ladders much easier to invert.

### 2. Price bundle ladders as a group

Products that represent the same virtual good at different quantities should be
solved together, not independently.

Examples:
- `credits_10`, `credits_25`, `credits_50`
- `coins_small`, `coins_medium`, `coins_large`

In `perfectdeckcli`, grouped products should declare:
- `base_usd`
- `units`
- optional `value_group`

### 3. Enforce non-increasing unit price

Within a bundle group, larger packs must never have a worse unit price than
smaller packs in the same market.

Required invariant per country:

`smaller_pack_price / smaller_pack_units >= larger_pack_price / larger_pack_units`

Strictly better value is preferred, but not required when a store price grid
makes it impossible without distorting the ladder too much.

### 4. Treat `.99` as a preference, not a constraint

Psychological endings are useful only when they do not violate:
- the upward-only floor
- the bundle value ladder

If a `.99` point breaks bundle economics, the bundle economics win.

## When To Use Store-Localized Automatic Prices

Prefer store-managed localized pricing when:
- the product is a single standalone one-time purchase with no bundle ladder
- the product has no meaningful `price per unit` comparison against sibling SKUs
- you want stores to keep adjusting local prices over time for taxes, FX, and
  local conventions

Examples:
- one-time unlocks
- ad removal
- a single consumable with no larger/smaller packs

## When To Use Explicit Regional Overrides

Prefer `perfectdeckcli`-generated explicit regional prices when:
- you have a bundle ladder and unit economics matter
- store-localized prices would make a larger pack equal or worse value than a
  smaller pack
- you need PPP-based differentiation that the store default does not express
- pricing is part of deliberate monetization design, not just localization

Examples:
- credit packs
- coin packs
- gem packs
- token bundles

## Recommended Product Modeling

For grouped consumables, define products like this:

```json
{
  "credits_10": {
    "base_usd": 1.99,
    "units": 10,
    "value_group": "credits"
  },
  "credits_25": {
    "base_usd": 3.99,
    "units": 25,
    "value_group": "credits"
  },
  "credits_50": {
    "base_usd": 6.99,
    "units": 50,
    "value_group": "credits"
  }
}
```

## Operational Guidance

For a new bundle ladder:

1. Set the intended US/base prices first.
2. Group related packs with `units` and `value_group`.
3. Generate regional prices.
4. Review exception markets where store grids compress price spacing.
5. If needed, adjust the base ladder rather than forcing prettier endings.

## Summary

The pricing engine should optimize for monetization coherence, not for `.99`
cosmetics. The hard rule is that bigger bundles cannot become worse value after
regional conversion and snapping.
