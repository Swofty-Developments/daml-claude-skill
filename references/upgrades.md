# Smart Contract Upgrades (SCU) in Daml 3

Splice runs on Daml 3.x with LF 2.1 (`--target=2.1` in every `daml.yaml`). SCU is the mechanism for evolving package contents — adding fields, choices, interface implementations — *without* breaking existing contracts on the ledger or in flight in client commands.

## What's checked, when

| Check | When |
|---|---|
| Module-level structural compatibility | At `daml build` (compile time) |
| Package upload conflict (same name, incompatible LF) | At `daml ledger upload-dar` |
| Contract value compatibility | At runtime, on every fetch / exercise that crosses package versions |

## Allowed changes (additive)

- Add a new template.
- Add a new `Optional` field with default `None` to an existing template.
- Add a new choice to an existing template (consuming or non-consuming).
- Add a new interface implementation.
- Add a new variant constructor *at the end* of a sum type.
- Tighten an `ensure` clause cautiously (rejects new contracts; existing ones unaffected).

## Forbidden changes

- Remove or rename any field of a template.
- Change the type of a field (`Decimal` → `Numeric 8`, `Party` → `Optional Party`, …).
- Add a non-Optional field to an existing template.
- Change `signatory`, `observer`, `key`, `maintainer`, or `controller` expressions in a way that alters the resulting party set.
- Change a choice's controller, observer, return type, or argument list.
- Reorder or remove sum type constructors.
- **Interfaces are not upgradable** — period. Once published, the interface module is frozen. To "evolve" an interface, ship a new package (`splice-api-foo-v2`) with a renamed module.
- **Exceptions are not upgradable** either — same rule.

## The V1 / V2 split pattern

Splice's canonical approach for breaking changes is to publish a new package with a versioned module name and let a single template implement *both* interfaces:

```
splice-api-featured-app-v1/   (module Splice.Api.FeaturedAppRightV1)
splice-api-featured-app-v2/   (module Splice.Api.FeaturedAppRightV2)
```

Both packages can have `version: 1.0.0` — they're distinct because their *names* and *modules* differ. The implementing template lives in a third package and provides two `interface instance` blocks:

```daml
-- splice/daml/splice-amulet/daml/Splice/Amulet.daml
template FeaturedAppRight with dso, provider where
  signatory dso
  observer provider
  interface instance Splice.Api.FeaturedAppRightV1.FeaturedAppRight for FeaturedAppRight where
    view = Splice.Api.FeaturedAppRightV1.FeaturedAppRightView with dso, provider
    ...
  interface instance Splice.Api.FeaturedAppRightV2.FeaturedAppRight for FeaturedAppRight where
    view = Splice.Api.FeaturedAppRightV2.FeaturedAppRightView with dso, provider
    ...
```

Old clients import V1 and continue working; new clients import V2 and get the richer surface. No on-ledger contract is migrated.

## Deprecating a choice in place

When you can't remove a choice (existing transactions reference it) but want to retire it, replace its body with `deprecatedChoice`:

```daml
choice Amulet_Expire : Amulet_ExpireResult
  with roundCid : ContractId OpenMiningRound
  controller dso
  do deprecatedChoice "splice-amulet" "0.1.17" "Amulet_Expire"

choice Amulet_ExpireV2 : Amulet_ExpireV2Result
  with externalPartyConfigState0Cid : ContractId ExternalPartyConfigState
       externalPartyConfigState1Cid : ContractId ExternalPartyConfigState
  controller dso
  do ...
```

`deprecatedChoice` is `Splice.Util.deprecatedChoice : Text -> Text -> Text -> Update a` and is just `abort ("Choice " <> show choice <> " is no longer supported since " <> show package <> "-" <> show version)`. The signature remains for compatibility; the body fails fast with a clear message that points to the new version.

## Result-record forward compatibility

Splice's choices return named record types — never tuples — so adding a new field is upgrade-safe:

```daml
data TransferOffer_AcceptResult = TransferOffer_AcceptResult with
    acceptedTransferOffer : ContractId AcceptedTransferOffer
-- later:
data TransferOffer_AcceptResult = TransferOffer_AcceptResult with
    acceptedTransferOffer : ContractId AcceptedTransferOffer
    meta                  : Optional Metadata   -- new field, Optional, defaults None
```

Old callers destructuring by name keep working; new callers can read `meta`.

## "Compatible at compile, broken at runtime" pitfalls

1. **Changing semantics of a field name without changing the type.** E.g. `expiresAt` was inclusive, now exclusive. Compile-clean, behavior subtly broken. The fix: add a new field name, leave the old one alone.
2. **Re-interpreting a controller expression.** Same parties, same type, but the *order* of evaluation differs and now hits a different branch. Compile-clean, authorization fails at runtime. The fix: cover this with explicit upgrade tests that re-exercise old contracts under the new code.
3. **Adding an `ensure` clause.** Existing contracts pass through (the clause runs only at create time), but every new create from old client code now fails `PreconditionFailed`. The fix: only tighten ensure when the deployed clients have already been updated.
4. **Implementation type drift in a `view`.** A `view` that uses a stdlib function whose semantics shift between LF versions can crash on old contracts. Keep `view` arithmetic boring.

## Verifying upgrade safety locally

```bash
cd path/to/splice-myfeature
daml build                              # canonical version
mv .daml/dist/splice-myfeature-0.1.0.dar /tmp/v1.dar

# edit code, bump version
daml build                              # candidate upgrade
daml damlc inspect-dar .daml/dist/splice-myfeature-0.1.1.dar | head -50
# Compare module hashes; check that template field lists match V1 + Optional additions only.
```

The compile-time checker rejects most violations. For the runtime ones (semantic drift), write a test in a `*-test` package that creates a V1 contract via `data-dependencies` on V1's DAR, then exercises V2 choices on it.

## Reference: where the canonical examples live

| Pattern | File |
|---|---|
| V1/V2 split | `splice/daml/splice-api-featured-app-v1/`, `splice/daml/splice-api-featured-app-v2/` |
| Single template, multiple impls | `splice/daml/splice-amulet/daml/Splice/Amulet.daml:271-301` |
| `deprecatedChoice` helper | `splice/daml/splice-util/daml/Splice/Util.daml:245-247` |
| Deprecated choice in use | `splice/daml/splice-amulet/daml/Splice/Amulet.daml:136` |
| Result-record forward compat | every `data *_Result` in `splice/daml/splice-wallet/daml/Splice/Wallet/TransferOffer.daml` |
