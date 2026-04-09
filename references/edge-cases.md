# Daml edge cases and subtle correctness

The stuff that compiles but is wrong, or eats half a day when you don't know it. Source citations are to the local repos under `~/Developer/daml/`.

## A. Authorization, visibility, divulgence

### A.1 Who must authorize what

| Action | Authority required |
|---|---|
| `create T` | All `signatory T` parties must be in the transaction's authority set |
| `exercise cid Choice` | All `controller` parties of the choice |
| `archive cid` | At least one signatory of the contract |
| `fetch cid` | The submitter must be a stakeholder (signatory or observer) — otherwise `INFORMATION_DISCLOSURE` from Canton, or `requires authorizers ...` at type-check time |

The compiler infers authority within a transaction tree from controllers and signatories already in scope. If you need extra authority, you must either submit as multiple parties (`submitMulti [a, b] [] $ ...`) or arrange for a signatory of one contract to exercise a choice on another.

### A.2 Multi-party `controller` via list cons

`splice/daml/splice-amulet/daml/Splice/Amulet.daml:185-189`:

```daml
choice LockedAmulet_Unlock : LockedAmulet_UnlockResult
  with openRoundCid : ContractId OpenMiningRound
  controller amulet.owner :: lock.holders   -- BOTH must sign
  do deprecatedChoice "splice-amulet" "0.1.17" "LockedAmulet_Unlock"
```

`amulet.owner :: lock.holders` builds a `[Party]` controller list — every party in it must authorize the exercise. This is non-obvious: there's no automatic discovery of who the lock holders are; the caller must arrange a transaction whose authority set contains all of them.

### A.3 Choice observers (the `observer` keyword inside a choice)

`splice/daml/splice-api-featured-app-v2/daml/Splice/Api/FeaturedAppRightV2.daml:37`:

```daml
nonconsuming choice FeaturedAppRight_CreateActivityMarker : FeaturedAppRight_CreateActivityMarkerResult
  with beneficiaries : [AppRewardBeneficiary]; weight : Optional Decimal
  observer (view this).provider :: map (.beneficiary) beneficiaries
  controller (view this).provider
  do featuredAppRight_CreateActivityMarkerImpl this self arg
```

Choice observers:
- Do NOT need to authorize.
- WILL see the choice's exercise node and all consequences.
- Are computed at exercise time from the args / template state, so they can be dynamic.

Why it bites: dynamically computed observers add stakeholders retroactively, which affects downstream visibility and can leak state if you're not careful.

### A.4 Divulgence and the checked-fetch antidote

Divulgence = a party sees a contract not because they're a stakeholder, but because the contract's content was revealed during transaction execution (e.g., as the input of a `fetch` in a transaction they're a witness to). It's a footgun: divulged contracts don't show up in the recipient's ACS, can vanish on participant restart, and cannot be re-disclosed.

Splice's defense is `Splice.Util.HasCheckedFetch` (`splice/daml/splice-util/daml/Splice/Util.daml:64-108`):

```daml
class (Show t, Eq cgid, Show cgid) => HasCheckedFetch t cgid where
  contractGroupId : t -> cgid

fetchChecked : (HasFetch t, HasCheckedFetch t cgid) => cgid -> ContractId t -> Update t
fetchChecked expectedcgid cid = do
  co <- fetch cid
  checkContractGroupId expectedcgid cid co
```

Every fetch passes through `fetchChecked` (or its sibling `fetchAndArchive`, `fetchReferenceData`, `fetchPublicReferenceData`) with an explicit "contract group" — `ForDso with dso`, `ForOwner with dso, owner` — and fails fast if the fetched contract doesn't match. **Use these helpers, never raw `fetch`.**

### A.5 Disclosed contracts and `expectedAdmin` guards

The Daml side of explicit disclosure is the *guard pattern*. The factory contract is disclosed off-ledger to a sender, who exercises a `nonconsuming` choice on it. Without a guard, an attacker could substitute a malicious factory. Splice's pattern (`splice/token-standard/splice-api-token-transfer-instruction-v1/daml/Splice/Api/Token/TransferInstructionV1.daml:185-192`):

```daml
nonconsuming choice TransferFactory_Transfer : TransferInstructionResult
  with
    expectedAdmin : Party
      -- ^ Implementations MUST validate this matches the factory admin.
      -- Callers SHOULD get expectedAdmin from a trusted source.
    transfer : Transfer
    extraArgs : ExtraArgs
  controller transfer.sender
  do transferFactory_transferImpl this self arg
```

**Always include an `expectedAdmin` (or analogous) parameter on choices exposed via disclosed factories, and validate it inside the impl.**

### A.6 Authority cheat-sheet

| Concept | Authorizes? | Sees contract? |
|---|---|---|
| `signatory P` (template) | Yes | Yes |
| `observer P` (template) | No | Yes |
| `controller P` (choice) | Yes | Yes (must be a stakeholder) |
| `observer X` (choice) | No | Yes (sees the exercise node) |
| `maintainer P` (key) | Yes (for key ops) | Yes (for key lookups) |

## B. Interfaces

### B.1 `viewtype` is a *type*, not a runtime guarantee

`canton/community/daml-lf/tests/src/main/daml/interface-views/InterfaceViews.daml:26-51`:

```daml
interface I where viewtype View
template T3 with p : Party; a : Int
  where
    signatory p
    interface instance I for T3 where
      view = error "view crashed"   -- compiles fine, crashes at runtime
```

Lesson: don't put logic in `view`. It should be a pure projection of fields. If your view computation can fail, your interface contract is unusable.

### B.2 Interface instance syntax

```daml
interface FeaturedAppRight where
  viewtype FeaturedAppRightView
  featuredAppRight_CreateActivityMarkerImpl
    : ContractId FeaturedAppRight
    -> FeaturedAppRight_CreateActivityMarker
    -> Update FeaturedAppRight_CreateActivityMarkerResult
  nonconsuming choice FeaturedAppRight_CreateActivityMarker
      : FeaturedAppRight_CreateActivityMarkerResult
    with beneficiaries : [AppRewardBeneficiary]; weight : Optional Decimal
    observer (view this).provider :: map (.beneficiary) beneficiaries
    controller (view this).provider
    do featuredAppRight_CreateActivityMarkerImpl this self arg
```

Implementation (`splice/daml/splice-amulet/daml/Splice/Amulet.daml:286-301`):

```daml
interface instance Splice.Api.FeaturedAppRightV2.FeaturedAppRight for FeaturedAppRight where
  view = Splice.Api.FeaturedAppRightV2.FeaturedAppRightView with dso, provider
  featuredAppRight_CreateActivityMarkerImpl _self arg = do
    validateAppRewardBeneficiariesV2 arg.beneficiaries
    require "Weight >= 1.0"     (fromOptional 1.0 arg.weight >= 1.0)
    require "Weight <= 10000.0" (fromOptional 1.0 arg.weight <= 10000.0)
    let grouped = Map.fromListWithR (+) (map (\b -> (b.beneficiary, b.weight)) arg.beneficiaries)
    cids <- forA (Map.toList grouped) $ \(b, w) ->
      create FeaturedAppActivityMarker with dso, provider, beneficiary = b, weight = w * fromOptional 1.0 arg.weight
    pure (FeaturedAppRight_CreateActivityMarkerResult $ map toInterfaceContractId cids)
```

Required: `view`, plus every `*Impl` method declared on the interface. Interface choices delegate to those `*Impl` methods.

### B.3 A single template can implement multiple interfaces

```daml
interface instance Splice.Api.FeaturedAppRightV1.FeaturedAppRight for FeaturedAppRight where ...
interface instance Splice.Api.FeaturedAppRightV2.FeaturedAppRight for FeaturedAppRight where ...
```

This is the canonical pattern for V1→V2 evolution: keep the template, add a second interface implementation. Old clients keep working.

### B.4 `requires` (interface inheritance)

```daml
interface I3 requires I4 where
    viewtype EmptyInterfaceView
```

Any template implementing `I3` must also implement `I4`. Use this when a more-specific interface logically extends a more-general one.

### B.5 `toInterface` / `fromInterface` / `*ContractId`

| Function | Purpose |
|---|---|
| `toInterface @I (t : T)` | Upcast a template value to an interface value |
| `fromInterface @T (i : I)` | Downcast (returns `Optional T`) |
| `toInterfaceContractId @I (cid : ContractId T)` | Upcast a contract id |
| `fromInterfaceContractId @T (cid : ContractId I)` | Downcast a contract id (still typed-`ContractId T`, but its real template is checked at fetch) |
| `coerceInterfaceContractId @I2 (cid : ContractId I1)` | Reinterpret an interface cid as a different interface — used with disclosed contracts where the runtime type is known by the caller |

### B.6 `ExtraArgs`, `ChoiceContext`, `Metadata` (the off-/on-ledger split)

`splice/token-standard/splice-api-token-metadata-v1/daml/Splice/Api/Token/MetadataV1.daml`:

```daml
data AnyValue = AV_Text Text | AV_Int Int | AV_Decimal Decimal | AV_Bool Bool
  | AV_Date Date | AV_Time Time | AV_RelTime RelTime | AV_Party Party
  | AV_ContractId AnyContractId | AV_List [AnyValue] | AV_Map (TextMap AnyValue)

data ChoiceContext = ChoiceContext with values : TextMap AnyValue
  -- Off-ledger; supplied by the wallet at command-submission time. NEVER stored.
data Metadata     = Metadata     with values : TextMap Text
  -- On-ledger; recorded in the transaction. Use DNS-style keys.
data ExtraArgs    = ExtraArgs    with context : ChoiceContext; meta : Metadata
```

Token-standard interface choices universally take `extraArgs : ExtraArgs`. The `ChoiceContext` is *not on-ledger* — the wallet computes it from off-chain state and passes it through command submission. Use it for things like which open-mining-round contract to use, fee adjustments from a backend, etc. Use `Metadata` for things you want preserved in the ledger record.

## C. Smart contract upgrades

See `references/upgrades.md`.

## D. Exceptions

### D.1 Syntax

```daml
exception E where message "E"
exception Ecid with cid : ContractId T where message "Ecid"

choice Throw : ()
  controller p
  do throw E

choice Catch : ()
  controller p
  do try (exercise self Throw) catch E -> pure ()
```

Multiple handlers via `|`:

```daml
try action
catch
  E1 -> handler1
  | E2 -> handler2
  | (e: SomeException) -> handler3
```

### D.2 Rollback semantics

Catching an exception creates a *rollback node*. Everything inside the `try` is undone (creates, archives), but ledger validation still applies — you can't fetch an inactive contract or violate key uniqueness inside a rollback. Actions in the `catch` handler **persist**.

`canton/.../exceptions/ExceptionSemantics.daml:69-99`:

```daml
nonconsuming choice TransientDuplicate : ()
  with i : Int
  controller p
  do try do create (K p i)
            create (K p i)   -- duplicate key inside try
            throw E
     catch E -> pure ()      -- both creates rolled back, no key conflict survives

nonconsuming choice RollbackKey : ()
  with i : Int
  controller p
  do try do create (K p i); throw E
     catch E -> create (K p i) >> pure ()   -- this create persists
```

Limitation: an exercise on an *inactive* contract cannot be caught — it's a hard transaction abort. Same for "info disclosure" failures. Don't try to use try/catch as a security retry loop.

### D.3 Splice's policy: `Either` for recoverable, exceptions for fatal

Splice prefers:

- `require "msg" cond` for assertions — uses `assertMsg` under the hood, throws `AssertionFailed`.
- Pure validators that return `Either Reason ()` (e.g. `checkTransferConstraints` in `AmuletRules.daml`).
- Sum-typed result variants for "this might fail in a known way":
  ```daml
  data TransferInstructionResult_Output
    = TransferInstructionResult_Pending   with transferInstructionCid : ContractId TransferInstruction
    | TransferInstructionResult_Completed with receiverHoldingCids   : [ContractId Holding]
    | TransferInstructionResult_Failed
  ```
- `exception` for fatal invariant violations and `deprecatedChoice` for retired choices.
- **Almost no `try`/`catch` in production choice bodies.** Let Canton surface failures.

### D.4 Built-in exceptions

- `AssertionFailed` — thrown by `assert`/`assertMsg`/`require`.
- `PreconditionFailed` — thrown when a template `ensure` clause fails.
- `ArithmeticError` — division by zero, overflow.
- `GeneralError` — `error "..."` in pure code.

## E. Time and non-determinism

### E.1 `getTime` semantics

`getTime` returns the *ledger time* the sequencer assigns to the transaction. Two calls in the same transaction return the same value. The value is bounded by the command's `min_ledger_time` / `max_ledger_time` and the participant's clock.

**Bind it once at the top of each choice and reuse:**

```daml
choice AppPaymentRequest_Accept : AppPaymentRequest_AcceptResult
  with inputs : [TransferInput]; context : PaymentTransferContext; walletProvider : Party
  controller sender, walletProvider
  do now <- getTime                       -- bind once
     contextRound <- fetchPublicReferenceData (ForDso with dso) ...
     amuletAmount <- paymentAmountToAmulet dso contextRound amount
     require "AppPaymentRequest has not expired" (now < expiresAt)
     let expiresAt' = max (addRelTime now contextRound.tickDuration) contextRound.targetClosesAt
     ...
```

### E.2 Ledger time vs record time

- *Ledger time* (`getTime`): the time the transaction logically observes. Used for all contract logic.
- *Record time*: when the sequencer recorded the transaction. Visible off-ledger, never in Daml. Don't try to reach for it.

### E.3 Deadline assertions

```daml
assertWithinDeadline   "Lock.expiresAt" lock.expiresAt   -- requires getTime <  deadline
assertDeadlineExceeded "Lock.expiresAt" lock.expiresAt   -- requires getTime >= deadline
```

At equality the deadline is *exceeded*. The two are mutually exclusive over the same value.

### E.4 Don't store `getTime` in field values

Storing `now` in a field of a created contract makes the contract content depend on ledger time, which makes re-interpretation non-deterministic. Always store *deadlines* (computed from the input that triggered the create), never "right now".

## F. Numerics

### F.1 Decimal

`Decimal` = `Numeric 10`. Range ±10²⁸ - 1, ten fractional digits. `+` and `-` are exact (subject to range). `*` and `/` round half-even to 10 places.

### F.2 Avoiding precision loss

- Multiply before dividing where possible.
- Compute fees on aggregate amounts, not per-item then summed.
- Use `min remainder step * currentRate` style stepped charging (`Splice.Fees`).
- For very large values that could overflow, use `Splice.Expiry.BoundedSet`:

```daml
data BoundedSet a = Singleton a | AfterMaxBound

boundedDivDecimal : Decimal -> Decimal -> BoundedSet Decimal
boundedDivDecimal x y
  | x <= 0.0 = error $ "boundedDivDecimal: negative first operand " <> show x
  | y <= 0.0 = error $ "boundedDivDecimal: negative second operand " <> show y
  | y < 1.0 && x > maxDecimalDiv10 * y = AfterMaxBound
  | otherwise = Singleton (x / y)
```

This is how Splice represents "amount is so large it never expires" without crashing.

### F.3 Common arithmetic bugs

| Bug | Fix |
|---|---|
| Subtracting then producing a negative balance | `require "sufficient" (have >= need)` first |
| Truncation from `(a * b) / c` when `a*b` is huge | Reorder, or use `BoundedSet` |
| Accumulating per-item fees | Charge on the aggregate |
| Overflow in round arithmetic | Use `RelRound`/`BoundedRound`, not raw `Int` |

## G. Daml-script reference

### G.1 Operations

```daml
-- Submission
submit             : Party   -> Commands a -> Script a
submitMulti        : [Party] -> [Party]    -> Commands a -> Script a    -- actAs / readAs
submitMustFail     : Party   -> Commands a -> Script ()
submitMultiMustFail: [Party] -> [Party]    -> Commands a -> Script ()

-- Querying
query              : forall t. Template t   => Party -> Script [(ContractId t, t)]
queryContractId    : forall t. Template t   => Party -> ContractId t -> Script (Optional t)
queryFilter        : forall t. Template t   => Party -> (t -> Bool)  -> Script [(ContractId t, t)]
queryInterface     : forall i. HasInterfaceView i v => Party -> Script [(ContractId i, Optional v)]
queryDisclosure    : Party -> ContractId t -> Script (Optional Disclosure)

-- Parties
allocateParty         : Text -> Script Party
allocatePartyWithHint : Text -> PartyIdHint -> Script Party

-- Time (only in static-time mode)
getTime  : Script Time
setTime  : Time    -> Script ()
passTime : RelTime -> Script ()
```

### G.2 Common pitfalls

- **Forgetting `passTime` when testing expiry.** If you create a contract with `expiresAt = now + hours 1` and then check expiry without advancing time, the test passes for the wrong reason.
- **Disclosed contracts in tests.** A choice that needs an `OpenMiningRound` will fail unless that contract is either visible to the caller or explicitly disclosed via `submitWithDisclosures`. Look at how `splice/daml/splice-amulet-test/daml/Splice/Scripts/Util.daml` handles this.
- **Party allocation order.** Allocation hints affect the resulting party id; don't depend on stable IDs across runs.
- **`submitMulti` `readAs`.** The second list lets the submitter *see* contracts owned by other parties without acting on their behalf. Forget it and you'll get "couldn't find contract" errors.

## H. Daml.yaml details

```yaml
sdk-version: 3.3.0-snapshot.20250502.13767.0.v2fc6c7e2   # pin exactly
name: splice-myfeature
source: daml
version: 0.1.0
dependencies:
  - daml-prim
  - daml-stdlib
  - daml-script   # if you have a Script in this package
data-dependencies:
  - ../splice-util/.daml/dist/splice-util-current.dar
  - ../../token-standard/splice-api-token-holding-v1/.daml/dist/splice-api-token-holding-v1-current.dar
build-options:
  - --target=2.1                   # REQUIRED for SCU / Daml 3
  - --ghc-option=-Wunused-binds
  - --ghc-option=-Wunused-matches
codegen:
  java:
    package-prefix: org.example.codegen.java
    output-directory: target/daml-codegen-java
```

- **`dependencies`** — only stdlib + framework, never your own packages.
- **`data-dependencies`** — DAR files of other packages (yours or third-party). The compiler reads the LF model out of the DAR; you can implement interfaces and reference templates.
- **`--target=2.1`** — universal in Splice; gates Daml-LF 2.1 features (interfaces, exceptions, SCU).
- **No `module-prefixes:` and no `upgrades:`** in modern Splice. Both were Daml 2.x and aren't used in Daml 3.

## I. Common compile / runtime errors

| Error | Cause | Fix |
|---|---|---|
| `requires authorizers ..., but only ... were given` | The transaction's authority set is missing a signatory or controller | `submitMulti` with all needed parties, or arrange a delegation chain |
| `Tried to fetch a contract of type X but found Y` | Contract id pointed at the wrong template | Use `fetchChecked` with explicit group id |
| `Pattern match(es) are non-exhaustive` | Missing case in `case ... of` | Add the case or `_ -> error "..."` |
| `Could not deduce ... arising from a use of ...` | Missing typeclass — usually a missing import (`DA.Assert`, `DA.Optional`) or missing `deriving (Eq, Show)` | Add the import / derive |
| `Couldn't match type Numeric N with Numeric M` | Mixing precisions | Stay in `Decimal` everywhere |
| `Variable not in scope` | Typo or missing import | Spell-check, add import |
| `Conflicting upgrade` | Incompatible package change (removed field, type change, controller change) | Add field as `Optional` with default; never remove |
| `INFORMATION_DISCLOSURE` (Canton runtime) | Submitter not a stakeholder of a contract they tried to fetch | Add as observer, or pass via explicit disclosure |
| `PreconditionFailed` | A template's `ensure` clause failed at create time | Either the input is wrong, or your invariant is too strict |
| `ContractNotActive` | Tried to exercise a choice on an already-archived contract | Re-fetch the latest cid before exercising |
| `GUARD_FAILED` | Internal Daml engine bug (very rare) | File against Digital Asset |

## J. Misc patterns Splice uses

### J.1 Language extensions

```daml
{-# LANGUAGE ApplicativeDo #-}
{-# LANGUAGE MultiWayIf #-}
```

`ApplicativeDo` lets the compiler reorder independent binds inside `do` blocks (small perf win, occasionally readability). `MultiWayIf` enables:

```daml
if | x < 0     -> "neg"
   | x == 0    -> "zero"
   | otherwise -> "pos"
```

### J.2 Module organization

1. Copyright header (Apache 2.0)
2. `{-# LANGUAGE ... #-}` pragmas
3. `module Splice.X where`
4. Imports (Prelude, then `DA.*`, then `Splice.*`)
5. Pure data types
6. Pure helper functions
7. Templates (and their choices)
8. `interface instance` blocks
9. Trailing utility functions

### J.3 Pure helpers in `let` bindings

Splice extracts non-Update logic into pure functions and calls them from choice bodies via `let`. Keeps choice bodies short and testable in isolation.
