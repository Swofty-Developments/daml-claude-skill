---
name: daml
description: Production Daml on Canton Network — templates, choices, interfaces, propose/accept, token-standard implementations, transfers, subscriptions, locking, upgrades, exceptions, testing, and the local verify loop. Use when writing or modifying .daml files, designing Daml workflows, implementing CIP token-standard interfaces (Holding/Transfer/Allocation/Metadata), or building Splice/Canton applications.
---

# Writing Daml the Splice way

You are writing Daml that will run on Canton. The reference for "production-grade Daml" is the Hyperledger Splice codebase (Amulet, Wallet, DSO governance, ANS, Splitwell) and the Canton Network token-standard interfaces. **Read them when in doubt — don't guess.**

## Setup: locate the reference corpus

Run this once at the start of any session where you might need to consult the reference repos (idempotent, ~50 ms when repos exist, ~60 s on first clone). The script works on macOS, Linux, and Windows — it uses Python 3 and `git`, both of which are present on any Daml dev machine.

```bash
# macOS / Linux
python3 "${CLAUDE_SKILL_DIR}/scripts/ensure_refs.py"
```

```powershell
# Windows (PowerShell)
python "$env:CLAUDE_SKILL_DIR\scripts\ensure_refs.py"
```

Capture the printed path as `$DAML_REFS` and use it as the base for every subsequent `grep` or `Read`. Resolution order: `$DAML_REFS` env var → `~/Developer/daml/` → OS-appropriate cache (`~/.cache/daml-claude-skill/refs` on mac/Linux, `%LOCALAPPDATA%\daml-claude-skill\refs` on Windows). On first use in the cache branch, `canton`, `splice`, and `splice-wallet-kernel` are cloned shallow from GitHub.

Every file:line citation in this skill and its references is relative to that base, so `splice/daml/splice-amulet/daml/Splice/Amulet.daml:185` means `$DAML_REFS/splice/daml/splice-amulet/daml/Splice/Amulet.daml` at line 185.

The reference subdirectories under `$DAML_REFS`:

- `splice/daml/` — production app templates (Amulet, Wallet, DSO, ANS, Splitwell)
- `splice/token-standard/` — CIP interface contracts (HoldingV1, TransferInstructionV1, AllocationV1, MetadataV1, AllocationInstructionV1, AllocationRequestV1, BurnMintV1)
- `canton/` — Canton platform; canonical for upgrades, exceptions, interface tests
- `splice-wallet-kernel/` — TS wallet that exercises these contracts

Before writing non-trivial Daml, **grep these repos for an analogous contract and copy its shape**. The Splice authors have made a lot of subtle decisions; reproducing them is almost always right.

## The five rules

1. **Don't invent, mimic.** A transfer? Read `Splice/Wallet/TransferOffer.daml` and `Splice/Amulet/TwoStepTransfer.daml`. A subscription? `Splice/Wallet/Subscriptions.daml`. A token? `Splice/Amulet.daml`. A factory? `Splice/Api/Token/TransferInstructionV1.daml`.
2. **Avoid contract keys.** Splice uses contract IDs and ACS queries exclusively. Default answer: no key.
3. **One template per state-machine phase.** Don't archive-and-recreate to add a signatory. Model `Offer → Accepted → Completed` as separate templates with widening signatory sets.
4. **Choices return named records, never tuples.** This keeps result types forward-compatible across upgrades.
5. **Implement the token standard interfaces.** Don't invent your own asset/transfer/allocation/metadata interface — implement `HoldingV1` / `TransferInstructionV1` / `AllocationV1` / `MetadataV1` / `BurnMintV1`.

Plus three smaller hard rules:
- `Decimal`, never `Numeric n`, for amounts.
- `getTime` is for **decisions** in choice bodies, never for **field values**. Bind it once per choice and reuse.
- Always `fetchChecked` (`Splice.Util`), never raw `fetch`.

## Verify locally — non-negotiable

Every time you write or edit a `.daml` file:

```bash
cd <package-with-daml.yaml>
daml build       # must succeed; fix every error before continuing
daml test        # must pass; covers all Scripts in the package
```

A change is **not done** until both pass. If `daml` isn't installed: `curl -sSL https://get.daml.com/ | sh -s -- --install-with-hash`, then `export PATH="$HOME/.daml/bin:$PATH"`. If the SDK version doesn't match the project's `daml.yaml` pin: `daml install project`. Full setup notes: [`references/local-setup.md`](references/local-setup.md).

Splice's repos pin SDK `3.3.0-snapshot.20250502.13767.0.v2fc6c7e2`. If you're working in a Splice subproject, run from inside the package directory so `daml.yaml` is picked up. The full SBT/nix outer build is *not* the loop you want — `daml build && daml test` in the package is.

## Package layout

```
{project}-v1/
├── daml.yaml
└── daml/
    └── {Project}/
        └── V1/
            ├── Token.daml                    -- one template per file
            ├── TokenInstrument.daml
            ├── TokenFactory.daml
            ├── TokenTransferFactory.daml
            ├── TokenBurnMintFactory.daml
            ├── TokenTransferInstruction.daml
            ├── TokenAllocation.daml
            ├── Token/
            │   ├── StandardInterfaces.daml   -- project-specific interfaces
            │   └── Util.daml                 -- helpers + cross-cutting types
            ├── CantoryRules.daml
            ├── CantoryLicensedFactory.daml
            ├── PendingLicensePayment.daml
            └── CantoryProxy.daml

{project}-v1-test/
├── daml.yaml                                  -- depends on ../{project}-v1/.daml/dist/...dar
└── daml/
    └── {Project}/
        └── V1/
            └── Scripts/
                ├── TestToken.daml
                ├── TestCantoryProxy.daml
                ├── TestCantoryLicense.daml
                ├── FindFeaturedAppRight.daml
                └── SetupMainnetFactory.daml
```

Modeled after splice-amulet. Hard rules from Kevin's review of the Cantory daml restructure:

- **Two packages: `{project}-v1` (prod) and `{project}-v1-test` (scripts).** Tests never live in the prod package; they live in a sibling that depends on the built `.dar`.
- **Version-namespace the directory.** Templates live under `{Project}/V1/`, so the module name is `{Project}.V1.Token`, not `{Project}.Token`. Future v2 lives at `{Project}/V2/` in a `{project}-v2` package.
- **One template per file at the top level.** No more grab-bag `Token.daml` containing every template. Each template gets its own `.daml` file named after the template (`Token.daml`, `TokenFactory.daml`, `TokenTransferFactory.daml`, `TokenBurnMintFactory.daml`, `TokenTransferInstruction.daml`, `TokenAllocation.daml`, `TokenInstrument.daml`, `CantoryRules.daml`, `CantoryProxy.daml`, …).
- **Helpers go in a sibling `Foo/` subdirectory.** Things like `createActivityMarker`, `consumeInputHoldings`, and shared records (`FeaturingConfig`) live in `Token/Util.daml`. Keep `Util.daml` template-free so every `Token*.daml` file can import it without cycles.
- **Project-specific interface definitions live in `Foo/StandardInterfaces.daml`.** Templates implement them via the same `interface instance` mechanism as the splice CIP interfaces.

Naming:
- Package: `{project}-v1` (lowercase, hyphen, version-suffixed). Tests in `{project}-v1-test`.
- Module: `{Project}.V1.{Thing}` for prod, `{Project}.V1.Scripts.{TestName}` for tests.
- Templates: singular noun (`Token`, `TokenInstrument`, `CantoryProxy`). The DAML template name should reflect *what the contract is* — call the registry-of-instruments `TokenInstrument`, not `TokenRegistry` (a registry shows all instruments; one instance is one instrument).
- Choices: `TemplateName_Action` (`Token_Transfer`, `TokenFactory_Mint`, `CantoryProxy_CreateToken`). When you rename a template, rename every choice in lockstep.
- Result types: `TemplateName_ActionResult` records, even for single-field returns.

`daml.yaml` skeleton:

```yaml
sdk-version: 3.3.0-snapshot.20250502.13767.0.v2fc6c7e2
name: splice-myfeature
source: daml
version: 0.1.0
dependencies:
  - daml-prim
  - daml-stdlib
  - daml-script
data-dependencies:                            # NOT dependencies — for cross-package contracts
  - ../splice-util/.daml/dist/splice-util-current.dar
  - ../../token-standard/splice-api-token-holding-v1/.daml/dist/splice-api-token-holding-v1-current.dar
build-options:
  - --target=2.1                              # required for Daml 3 / SCU
  - --ghc-option=-Wunused-binds
  - --ghc-option=-Wunused-matches
```

## Templates

### Signatory and observer choices

| Situation | Pattern |
|---|---|
| Owned asset (Amulet) | `signatory dso, owner` |
| Offer (one party initiates) | `signatory sender; observer receiver` |
| Accepted offer (both committed) | `signatory sender, receiver` |
| Operator-mediated state | `signatory dso, sender, receiver` |

After acceptance, hand off to a new template with the union signatory set — never archive-and-recreate to add signatories.

### `ensure` for create-time invariants

For *structural* invariants only (positive amounts, well-formed metadata). Anything that depends on ledger state belongs in a choice body.

```daml
ensure payDataIsValid payData
```

### No keys

Splice has zero contract keys in production. Use `ContractId` and ACS queries. Keys force serialization, prevent parallel submission, and create consistency footguns. If you think you need one, you almost certainly don't.

## Choices

### Consumption modes

- **default (consuming)** for state transitions.
- **`nonconsuming`** for read-only or factory-style choices (`AmuletRules_ComputeFees`, `TransferFactory_Transfer`).
- **`preconsuming` / `postconsuming`** are rare — only when you need the contract's visibility (or archive) at a specific point in the body.

### Always return named records

```daml
data TransferOffer_AcceptResult = TransferOffer_AcceptResult with
    acceptedTransferOffer : ContractId AcceptedTransferOffer

choice TransferOffer_Accept : TransferOffer_AcceptResult
  controller receiver
  do
    now <- getTime
    require "Offer has not expired" (now < expiresAt)
    cid <- create AcceptedTransferOffer with ..
    pure TransferOffer_AcceptResult with acceptedTransferOffer = cid
```

`with ..` (RecordWildCards) is the Splice idiom for copying same-named fields out of the surrounding template.

### Authorization with `controller actor` + `require`

When the controller is delegated via a choice argument, validate it inside the body:

```daml
choice TransferOffer_Expire : TransferOffer_ExpireResult
  with actor : Party
  controller actor
  do
    now <- getTime
    require "Contract has expired" (this.expiresAt <= now)
    require "Actor is a stakeholder" (actor `elem` stakeholder this)
    pure TransferOffer_ExpireResult
```

`require` is `Splice.Util.require : Text -> Bool -> Update ()`. Prefer it over `assertMsg` for consistency with the rest of the codebase.

## The propose/accept/reject (offer) pattern

The full offer/accept skeleton lives in [`references/cheatsheet.md`](references/cheatsheet.md). The shape:

- `Offer` template: `signatory sender; observer receiver`.
  - `_Accept` (controller `receiver`) → creates `AcceptedOffer`
  - `_Reject` (controller `receiver`)
  - `_Withdraw` (controller `sender`)
  - `_Expire` (controller `actor : Party`, with `require` stakeholder check)
- `AcceptedOffer` template: `signatory sender, receiver`.
  - `_Complete` (controller `sender, walletProvider`) — actual side effect
  - `_Withdraw` (controller `receiver`) — receiver still gets out
  - `_Abort` (controller `sender`) — sender still gets out

Always provide all four exits on each phase. Always return a named result record.

## Token-standard interfaces

If your asset is fungible, implement `Splice.Api.Token.HoldingV1.Holding`:

```daml
interface instance Holding for MyAsset where
  view = HoldingView with
    owner
    instrumentId = InstrumentId with admin = issuer; id = "MYTKN"
    amount       = this.amount
    lock         = None
    meta         = emptyMetadata
```

For transfers, implement `TransferInstructionV1.TransferInstruction` and expose a `TransferFactory` (nonconsuming, disclosed). The factory's `expectedAdmin` argument is **mandatory** — it prevents factory-substitution attacks. Always check it inside the impl:

```daml
nonconsuming choice TransferFactory_Transfer : TransferInstructionResult
  with expectedAdmin : Party; transfer : Transfer; extraArgs : ExtraArgs
  controller transfer.sender
  do require "expectedAdmin matches" (expectedAdmin == admin)
     transferFactory_transferImpl this self arg
```

Token-standard interface choices universally take an `extraArgs : ExtraArgs` parameter. `ExtraArgs` carries an off-ledger `ChoiceContext` (supplied by the wallet at command-submission time, never stored) and an on-ledger `Metadata` (stored in the transaction). Use `ChoiceContext` for things like which `OpenMiningRound` cid to use; use `Metadata` for things you want preserved on-ledger.

For DvP/atomic settlement, implement `AllocationV1`. For burn/mint, `BurnMintV1`. Pick the existing interface — never invent your own.

Canonical impls to read:
- `splice/daml/splice-amulet/daml/Splice/Amulet.daml` — Holding
- `splice/daml/splice-amulet/daml/Splice/AmuletTransferInstruction.daml` — TransferInstruction
- `splice/daml/splice-amulet/daml/Splice/Amulet/TwoStepTransfer.daml` — prepare/execute helpers
- `splice/daml/splice-amulet/daml/Splice/AmuletAllocation.daml` — Allocation

## Subscriptions (recurring payments)

The state machine, documented at the top of `Splice/Wallet/Subscriptions.daml`:

```
SubscriptionRequest
  --AcceptAndMakePayment-->  SubscriptionInitialPayment
                                  --Collect--> Subscription + SubscriptionIdleState + Amulet
                                                         |
                                                         v
                                                  --MakePayment--> SubscriptionPayment
                                                                     --Collect--> SubscriptionIdleState
```

- `Subscription` (immutable) is created once and *referenced by cid* by every state contract. Archiving it terminates the whole flow.
- `SubscriptionIdleState` is the resting state between charges; holds `nextPaymentDueAt`.
- `SubscriptionPayment` is in-flight, holding a `LockedAmulet` with `holders = [provider, receiver]` so the receiver can force-unlock if the sender vanishes.
- All key contracts use `signatory [sender, receiver, provider]`.

Copy the shape exactly when building any recurring-payment feature.

## Time, locking, expiry

```daml
do
  now <- getTime                     -- bind ONCE per choice
  require "expired" (deadline <= now)
  -- never: create Foo with createdAt = now
```

Lock pattern via `Splice.Expiry.TimeLock`:

```daml
TimeLock with
  holders    = dedupSort [provider, receiver]
  expiresAt
  optContext = Some "amulet-subscription: ..."
```

Use `Splice.Util.assertWithinDeadline` / `assertDeadlineExceeded` rather than open-coded comparisons. At equality the deadline is **exceeded**.

## Numerics

- `Decimal` everywhere (`Numeric 10`, ten fractional digits, ±10²⁸).
- Round in the user's favor (down for fees, down for what you charge).
- Use `Splice.Fees`-style stepped charging (`min remainder step * currentRate`).
- For very large values that could overflow, use `Splice.Expiry.BoundedSet` (`Singleton x | AfterMaxBound`).
- Accumulate fees on aggregates, not per-item.

## Error handling

```daml
require "Offer has not expired" (now < expiresAt)
```

For richer validators, return `Either Reason ()` from a pure function and convert at the choice boundary:

```daml
exception InvalidTransfer with reason : InvalidTransferReason
  where message show reason
```

Splice avoids `try`/`catch` in production choice bodies — the rollback semantics are subtle (see [`references/edge-cases.md`](references/edge-cases.md) §D) and Canton's failure handling is the right place for surfacing errors. Reserve exceptions for fatal invariants.

## Helper typeclasses you must use

From `Splice.Util`:

- **`HasCheckedFetch t cgid`** — every fetch goes through `fetchChecked expectedCgid cid`. Implement it for your view types so you can never accidentally mix DSO/owner groups.
- **`fetchAndArchive`**, **`fetchReferenceData`**, **`fetchPublicReferenceData`** — name the intent of every fetch.
- **`Patchable a`** — three-way merge for config updates.
- **`require : Text -> Bool -> Update ()`** — preferred assertion.
- **`deprecatedChoice : Text -> Text -> Text -> Update a`** — for retired choices.

## Upgrades (SCU)

Splice runs Daml 3 with `--target=2.1`. Upgrade-safe changes:

- Add a template, an Optional field, a choice, an interface implementation.
- Add a sum-type variant *at the end*.

Forbidden:

- Remove or rename fields. Change field types. Add a non-Optional field.
- Change `signatory`, `observer`, `controller`, `key`, or `maintainer` semantics.
- Reorder or remove sum-type constructors.
- **Interfaces and exceptions are not upgradable.** To evolve them, ship a new package with a versioned module name (`splice-api-foo-v2`).

The V1/V2 pattern: keep the implementing template and provide *two* `interface instance` blocks for V1 and V2. To retire a choice in place, replace its body with `deprecatedChoice "package" "version" "ChoiceName"`.

Full SCU rules and pitfalls: [`references/upgrades.md`](references/upgrades.md).

## Daml-Script tests

Tests live in a sibling `*-test` package under `daml/Splice/Scripts/`. The minimal pattern:

```daml
testHappyPath : Script ()
testHappyPath = script do
  alice <- allocateParty "Alice"
  bob   <- allocateParty "Bob"
  cid   <- submit alice $ createCmd Foo with ..
  TransferOffer_AcceptResult acceptedCid <- submit bob $ exerciseCmd cid TransferOffer_Accept
  Some accepted <- queryContractId bob acceptedCid
  accepted.amount === expected
```

Use `submitMulti [actAs] [readAs]` for multi-party authorization. Use `submitMustFail` / `submitMultiMustFail` for negative tests. Use `passTime (hours 2)` to test expiry — without it, the test passes for the wrong reason.

If a choice depends on a contract the submitter isn't a stakeholder of (e.g. an `OpenMiningRound`), it must be **explicitly disclosed** — see `splice-amulet-test/daml/Splice/Scripts/Util.daml`. Forgetting this is the most common Splice-test failure.

## Pitfalls Splice deliberately avoids

| Don't | Do |
|---|---|
| Add a `key` to enforce uniqueness | Use the contract id; query the ACS off-ledger |
| Archive + recreate to add a signatory | New template for the new phase |
| Return tuples from choices | Named `*Result` record |
| `Numeric n` for amounts | `Decimal` |
| Store `getTime` in a field | Use `getTime` only in choice-body decisions, bound once |
| Inline choice authority | `controller actor` + stakeholder `require` |
| Invent your own holding/transfer interface | Implement `HoldingV1` / `TransferInstructionV1` |
| `try`/`catch` in a choice | `require` up front; let Canton fail the tx |
| `dependencies` for cross-package contracts | `data-dependencies` |
| Raw `fetch cid` | `fetchChecked (ForOwner with dso; owner) cid` |
| Big monolithic choice body | Pure helpers + a thin orchestration |
| Multiple `getTime` calls in one choice | Bind once at the top |
| Skip `daml build` / `daml test` after editing | Always run both before declaring done |

## Reference files

For depth on anything above, the supporting files in this skill expand each topic with file:line citations from the local repos:

- [`references/edge-cases.md`](references/edge-cases.md) — authorization rules, choice observers, divulgence, interface subtleties (`viewtype`, `requires`, `toInterface`, `coerceInterfaceContractId`), `ExtraArgs`/`ChoiceContext`/`Metadata`, exceptions and rollback semantics, time and non-determinism, decimal precision, common compile/runtime errors.
- [`references/upgrades.md`](references/upgrades.md) — Smart Contract Upgrades: what's allowed, what isn't, V1/V2 split, `deprecatedChoice`, runtime pitfalls.
- [`references/local-setup.md`](references/local-setup.md) — installing the SDK, every CLI command, the dev loop, sandbox vs Canton, common install errors.
- [`references/cheatsheet.md`](references/cheatsheet.md) — copy-pasteable canonical patterns: module skeleton, full offer/accept, `HoldingV1` impl, `TransferFactory` impl, subscription state machine, checked fetch, test skeleton, `daml.yaml`.

## When the conventions here don't cover your case

1. `grep -r "template " ~/Developer/daml/splice/daml/ -l` and find the closest analogue.
2. Read the matching `*-test` package to see how the contract is exercised end-to-end.
3. Search the Daml docs (https://docs.daml.com/daml/patterns.html) for the named pattern.
4. If you're touching the token standard, the interface file in `splice/token-standard/` is the source of truth — every concrete implementation must match its method signatures exactly.
5. Then write code, run `daml build`, run `daml test`, and only then declare done.
