# Daml local toolchain on macOS

Everything Claude needs to install, build, and test Daml on this machine. The user works on Cantory and Walley and has Splice / Canton / splice-wallet-kernel cloned under `~/Developer/daml/`.

## 1. Install the Daml SDK

```bash
# One-shot installer (puts everything under ~/.daml/)
curl -sSL https://get.daml.com/ | sh -s -- --install-with-hash

# Add to PATH
export PATH="$HOME/.daml/bin:$PATH"

# Sanity check
daml version
```

The SDK is *not* on Homebrew. The installer downloads to `~/.daml/sdk/<version>/`, drops a launcher in `~/.daml/bin/daml`, and that launcher (the "daml assistant") delegates to per-version `damlc`, `daml-helper`, and `canton` binaries.

### Pinning to a project's version

`daml install project` (run from inside a `daml.yaml`-containing directory) installs whatever `sdk-version:` line that file declares. The Splice repos pin a specific snapshot:

```
sdk-version: 3.3.0-snapshot.20250502.13767.0.v2fc6c7e2
```

So:

```bash
cd ~/Developer/daml/splice/daml/splice-amulet
daml install project    # one-time; idempotent
daml version            # confirm the snapshot is now installed
```

### Splice's nix shell (optional, fuller env)

Splice ships a nix flake: `~/Developer/daml/splice/nix/flake.nix` plus `nix/shell.nix`. `direnv allow` in the splice root activates a shell with the pinned `daml`, the matching `canton` binary, `sbt`, `postgresql@14`, `node`, `protoc`, and a bunch of cluster tooling. If you're touching anything beyond a single Daml package, prefer the nix shell — it removes guesswork.

```bash
cd ~/Developer/daml/splice
direnv allow
daml --version
canton --version
```

For just writing/testing a daml package in isolation, the plain `daml install` is enough.

## 2. The CLI commands you actually use

```bash
# Scaffold
daml new my-pkg --template empty-skeleton    # bare-bones template
daml new my-pkg --template quickstart        # fully-worked example with ledger api code
daml init                                    # in an existing dir, generates daml.yaml

# Build (produces .daml/dist/<name>-<version>.dar)
daml build
daml clean && daml build                     # nuke .daml/ cache and rebuild

# Test (runs every Script in the package)
daml test
daml test --files daml/MyTest.daml           # restrict to one file

# Inspect a DAR
daml damlc inspect-dar .daml/dist/my-pkg-0.1.0.dar
daml damlc inspect-dar .daml/dist/my-pkg-0.1.0.dar --json | jq

# Lint
daml damlc lint daml/

# REPL (interactive Daml)
daml repl --ledger-host localhost --ledger-port 6865 --dar .daml/dist/my-pkg.dar

# Local sandbox (in-memory Canton, ephemeral)
daml sandbox                                 # default port 6865
daml start                                   # sandbox + Navigator UI + initial scripts

# Talk to a running ledger
daml ledger list-parties      --host localhost --port 6865
daml ledger allocate-parties  alice          --host localhost --port 6865
daml ledger upload-dar        my.dar         --host localhost --port 6865
daml ledger fetch-dar         --main-package-id <pkg-id>

# Run a script against a real ledger
daml script \
  --dar  .daml/dist/my-pkg-0.1.0.dar \
  --script-name MyTests:testHappyPath \
  --ledger-host localhost --ledger-port 6865

# Codegen
daml codegen js     # produces TS bindings under daml.js/
daml codegen java
```

## 3. The dev loop for a single Daml package

```bash
cd path/to/splice-myfeature
daml build                # cold ~10-30s, incremental <1s
daml test                 # runs all Scripts; PASS/FAIL + line numbers
```

After every meaningful edit:
1. `daml build` — must succeed.
2. `daml test` — all scripts must pass.

These two commands are the **definition of "the daml is correct"** for an iteration. If you skip them, you're guessing.

## 4. The dev loop in Splice's monorepo

Splice's outer build is SBT, which orchestrates Daml packages via `DamlPlugin`. From `~/Developer/daml/splice/build.sbt`, every Daml package (`splice-amulet`, `splice-wallet`, etc.) is registered as an sbt project with `damlBuild`/`damlTest` tasks. But for everyday work on a single package, `daml build` and `daml test` invoked *in that package directory* are equivalent and faster.

Top-level Splice convenience targets:

```bash
cd ~/Developer/daml/splice
make build       # full bundle (slow; needs nix shell + JFrog access)
sbt test         # full integration suite (slow; needs running Canton)
```

For Claude (and anyone else doing focused Daml work), **`cd <pkg> && daml build && daml test` is the pragmatic loop**, not the full sbt build.

## 5. Creating a fresh package from scratch

```bash
mkdir -p ~/Developer/scratch/my-first-daml/daml
cd ~/Developer/scratch/my-first-daml

cat > daml.yaml <<'YAML'
sdk-version: 3.3.0-snapshot.20250502.13767.0.v2fc6c7e2
name: my-first-daml
source: daml
version: 0.1.0
dependencies:
  - daml-prim
  - daml-stdlib
  - daml-script
build-options:
  - --target=2.1
YAML

cat > daml/MyTemplate.daml <<'DAML'
module MyTemplate where

template Asset
  with
    issuer : Party
    owner  : Party
    amount : Decimal
  where
    signatory issuer, owner
    ensure amount > 0.0

    choice Asset_Transfer : ContractId Asset
      with newOwner : Party
      controller owner
      do create this with owner = newOwner
DAML

cat > daml/MyTest.daml <<'DAML'
module MyTest where

import Daml.Script
import MyTemplate

testTransfer : Script ()
testTransfer = script do
  alice <- allocateParty "Alice"
  bob   <- allocateParty "Bob"
  cid   <- submitMulti [alice, bob] [] $ createCmd Asset with
    issuer = alice; owner = alice; amount = 100.0
  -- transfer requires owner authority only
  cid'  <- submit alice $ exerciseCmd cid Asset_Transfer with newOwner = bob
  Some asset <- queryContractId bob cid'
  asset.owner === bob
DAML

daml build
daml test
```

The first `daml build` will fail because `signatory issuer, owner` requires both to authorize the create — fix it by either using `submitMulti [alice, bob]` (already done) or by changing the signatory set. Use this loop to feel out the type checker.

## 6. Sandbox vs Canton vs Splice localnet

- **`daml sandbox`** — single in-memory participant + synchronizer, no auth, no persistence. Sufficient for unit-style flows: party allocation, two-party offer/accept, locking. **Use for any non-distributed test.**
- **Canton (full)** — needed when you want persistence, multiple participants, or to exercise cross-domain workflows. The Splice nix shell ships the matching `canton` binary; `splice/start-canton.sh` boots a participant + synchronizer in tmux.
- **Splice localnet** — the full Splice scan/validator/wallet stack, composed via SBT + scripts in `splice/scripts/`. **Not realistic for an AI agent to spin up end-to-end.** Don't try.

For "is this Daml correct?" the answer is almost always: write a Script and run `daml test`. That's it.

## 7. Verifying correctness without running

```bash
daml damlc lint daml/                  # warnings (unused binds, shadowing, etc.)
daml build                             # full type check + interface conformance
daml damlc inspect-dar .daml/dist/...  # see what the LF model looks like
```

`daml build` is the strongest static check — it runs the typechecker, ensures every interface implementation is complete, and verifies that all `data-dependencies` resolve. **If `daml build` is green, the code is at least type-correct.**

## 8. Common install / build problems

| Symptom | Cause | Fix |
|---|---|---|
| `daml: command not found` | `~/.daml/bin` not on PATH | `export PATH="$HOME/.daml/bin:$PATH"` (and add to `~/.zshrc`) |
| `Wrong SDK version` on `daml build` | The pin in `daml.yaml` isn't installed | `daml install project` |
| `Cannot find DAR` for a `data-dependency` | Dependent package not built yet | `cd ../splice-util && daml build`, then back |
| `Package conflict` on upload | Two DARs with same name + version but different content | Bump `version:` in `daml.yaml` |
| `Address already in use` on sandbox | Port 6865 taken (or 5000 by macOS AirPlay) | `daml sandbox --port 6866` or disable AirPlay receiver |
| Stale errors after edit | Cached `.daml/` artifacts | `daml clean && daml build` |
| `nix: command not found` in splice/ | Not in nix shell | `direnv allow` in `~/Developer/daml/splice` |

## 9. The mandatory verification step

When Claude writes or edits a `.daml` file in a project, the loop is:

1. Edit.
2. `cd` into the *package* (the directory containing `daml.yaml`).
3. `daml build` — must succeed. Fix every error before proceeding.
4. If you added or changed behavior, write or update a Script in the same package or its sibling `*-test` package.
5. `daml test` — must pass.
6. Only then report the change as done.

If `daml build` fails with a `data-dependencies` error, build the dependency first (`cd ../<dep> && daml build`) and return. If it fails with an SDK mismatch, run `daml install project`.
