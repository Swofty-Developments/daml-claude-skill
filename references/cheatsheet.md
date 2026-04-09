# Daml cheatsheet — copy-pasteable canonical patterns

Every snippet here is reduced from real Splice code under `~/Developer/daml/splice/`. Use them as starting points; don't change them gratuitously.

## Module skeleton

```daml
-- Copyright (c) 2024 Digital Asset (Switzerland) GmbH and/or its affiliates.
-- SPDX-License-Identifier: Apache-2.0

{-# LANGUAGE ApplicativeDo #-}

module Splice.MyFeature where

import DA.Assert
import DA.Optional
import DA.Time

import Splice.Util

-- pure types
data MyValue = MyValue with field : Decimal
  deriving (Eq, Show)

-- pure helpers
isValid : MyValue -> Bool
isValid v = v.field > 0.0

-- templates
template Foo with ...
  where
    signatory ...
```

## Two-template offer / accept

```daml
template TransferOffer with
    sender    : Party
    receiver  : Party
    dso       : Party
    amount    : Decimal
    expiresAt : Time
    trackingId: Text
  where
    signatory sender
    observer  receiver
    ensure amount > 0.0

    choice TransferOffer_Accept : TransferOffer_AcceptResult
      controller receiver
      do
        now <- getTime
        require "Offer has not expired" (now < expiresAt)
        cid <- create AcceptedTransferOffer with ..
        pure TransferOffer_AcceptResult with acceptedTransferOffer = cid

    choice TransferOffer_Reject : TransferOffer_RejectResult
      controller receiver
      do pure TransferOffer_RejectResult

    choice TransferOffer_Withdraw : TransferOffer_WithdrawResult
      controller sender
      do pure TransferOffer_WithdrawResult

    choice TransferOffer_Expire : TransferOffer_ExpireResult
      with actor : Party
      controller actor
      do
        now <- getTime
        require "Contract has expired"   (expiresAt <= now)
        require "Actor is a stakeholder" (actor `elem` stakeholder this)
        pure TransferOffer_ExpireResult

data TransferOffer_AcceptResult   = TransferOffer_AcceptResult   with acceptedTransferOffer : ContractId AcceptedTransferOffer
data TransferOffer_RejectResult   = TransferOffer_RejectResult
data TransferOffer_WithdrawResult = TransferOffer_WithdrawResult
data TransferOffer_ExpireResult   = TransferOffer_ExpireResult

template AcceptedTransferOffer with
    sender    : Party
    receiver  : Party
    dso       : Party
    amount    : Decimal
    expiresAt : Time
    trackingId: Text
  where
    signatory sender, receiver

    choice AcceptedTransferOffer_Complete : AcceptedTransferOffer_CompleteResult
      with walletProvider : Party
      controller sender, walletProvider
      do
        -- side effects (transfer execution) go here
        pure AcceptedTransferOffer_CompleteResult

    choice AcceptedTransferOffer_Withdraw : AcceptedTransferOffer_WithdrawResult
      controller receiver
      do pure AcceptedTransferOffer_WithdrawResult

    choice AcceptedTransferOffer_Abort : AcceptedTransferOffer_AbortResult
      controller sender
      do pure AcceptedTransferOffer_AbortResult

data AcceptedTransferOffer_CompleteResult = AcceptedTransferOffer_CompleteResult
data AcceptedTransferOffer_WithdrawResult = AcceptedTransferOffer_WithdrawResult
data AcceptedTransferOffer_AbortResult    = AcceptedTransferOffer_AbortResult
```

## Implementing `HoldingV1`

```daml
import qualified Splice.Api.Token.HoldingV1 as Holding

template MyAsset with
    issuer : Party
    owner  : Party
    amount : Decimal
  where
    signatory issuer, owner
    ensure amount > 0.0

    interface instance Holding.Holding for MyAsset where
      view = Holding.HoldingView with
        owner
        instrumentId = Holding.InstrumentId with admin = issuer; id = "MYTKN"
        amount
        lock = None
        meta = Holding.emptyMetadata
```

## Implementing a `TransferFactory`

```daml
import qualified Splice.Api.Token.TransferInstructionV1 as TI
import Splice.Util (require)

template MyTransferFactory with
    admin : Party
  where
    signatory admin

    interface instance TI.TransferFactory for MyTransferFactory where
      view = TI.TransferFactoryView with admin

      transferFactory_transferImpl _self arg = do
        require "expectedAdmin matches"
          (arg.expectedAdmin == admin)
        -- build TI.TransferInstructionResult here
        ...
```

## Subscription state machine

```daml
template SubscriptionRequest with
    subscriptionData : SubscriptionData
    payData : SubscriptionPayData
  where
    signatory subscriptionSignatories subscriptionData
    ensure payDataIsValid payData

    choice SubscriptionRequest_AcceptAndMakePayment : SubscriptionRequest_AcceptAndMakePaymentResult
      with inputs : [TransferInput]; ...
      controller subscriptionData.sender
      do ...

template Subscription with
    subscriptionData : SubscriptionData
  where
    signatory subscriptionSignatories subscriptionData

template SubscriptionIdleState with
    subscription : ContractId Subscription
    subscriptionData : SubscriptionData
    payData : SubscriptionPayData
    nextPaymentDueAt : Time
  where
    signatory subscriptionSignatories subscriptionData

    choice SubscriptionIdleState_MakePayment : SubscriptionIdleState_MakePaymentResult
      with ...
      controller subscriptionData.sender
      do ...

    choice SubscriptionIdleState_CancelSubscription : ...
    choice SubscriptionIdleState_ExpireSubscription : ...   -- any signatory after grace period
```

Locking pattern inside the payment step:

```daml
let lock = TimeLock with
      holders   = dedupSort [provider, receiver]
      expiresAt = nextDue
      optContext = Some $ "amulet-subscription: " <> subscriptionData.description
```

## Checked fetch

```daml
import Splice.Util

instance HasCheckedFetch HoldingView ForOwner where
  contractGroupId HoldingView{..} = ForOwner with
    dso   = instrumentId.admin
    owner

-- in a choice body:
holding <- fetchChecked (ForOwner with dso; owner = sender) holdingCid
```

## Daml-Script test skeleton

```daml
module Splice.Scripts.TestMyFeature where

import Daml.Script
import DA.Assert
import DA.Time

import Splice.MyFeature

testHappyPath : Script ()
testHappyPath = script do
  alice <- allocateParty "Alice"
  bob   <- allocateParty "Bob"
  dso   <- allocateParty "DSO"

  now <- getTime
  let expiresAt = addRelTime now (hours 24)

  offerCid <- submit alice $ createCmd TransferOffer with
    sender = alice; receiver = bob; dso; amount = 100.0; expiresAt
    trackingId = "test-1"

  TransferOffer_AcceptResult acceptedCid <-
    submit bob $ exerciseCmd offerCid TransferOffer_Accept

  Some accepted <- queryContractId bob acceptedCid
  accepted.amount === 100.0

testExpiredOfferRejected : Script ()
testExpiredOfferRejected = script do
  alice <- allocateParty "Alice"
  bob   <- allocateParty "Bob"
  dso   <- allocateParty "DSO"

  now <- getTime
  offerCid <- submit alice $ createCmd TransferOffer with
    sender = alice; receiver = bob; dso; amount = 100.0
    expiresAt = addRelTime now (seconds 1); trackingId = "test-2"

  passTime (seconds 5)

  submitMustFail bob $ exerciseCmd offerCid TransferOffer_Accept
```

## `daml.yaml` for a typical Splice-style package

```yaml
sdk-version: 3.3.0-snapshot.20250502.13767.0.v2fc6c7e2
name: splice-myfeature
source: daml
version: 0.1.0
dependencies:
  - daml-prim
  - daml-stdlib
  - daml-script
data-dependencies:
  - ../splice-util/.daml/dist/splice-util-current.dar
  - ../../token-standard/splice-api-token-holding-v1/.daml/dist/splice-api-token-holding-v1-current.dar
  - ../../token-standard/splice-api-token-metadata-v1/.daml/dist/splice-api-token-metadata-v1-current.dar
build-options:
  - --target=2.1
  - --ghc-option=-Wunused-binds
  - --ghc-option=-Wunused-matches
codegen:
  java:
    package-prefix: org.example.codegen.java
    output-directory: target/daml-codegen-java
```
