# daml-claude-skill

A [Claude Code skill](https://code.claude.com/docs/en/skills) that teaches Claude to write production-quality [Daml](https://www.digitalasset.com/developers) on [Canton Network](https://canton.network/).

Built from the canonical reference corpus: [Hyperledger Splice](https://github.com/hyperledger-labs/splice), the [Canton platform](https://github.com/digital-asset/canton), and the [Splice Wallet Kernel](https://github.com/hyperledger-labs/splice-wallet-kernel). Every convention is grounded in a real file:line citation from those repos, and the skill auto-clones them on first use — no manual setup required.

## What's in it

- **`SKILL.md`** — the entrypoint. Five hard rules, package layout, signatory/choice conventions, propose/accept handshake, token-standard interface implementations (`HoldingV1`, `TransferInstructionV1`, `AllocationV1`, `MetadataV1`, `BurnMintV1`), subscriptions, transfers, locking, upgrades summary, test skeleton, pitfall table, and the mandatory `daml build && daml test` verify loop.
- **`references/edge-cases.md`** — authorization rules, divulgence and the checked-fetch antidote, choice observers, multi-party controllers, every interface subtlety (`viewtype`, `requires`, `toInterface`, `coerceInterfaceContractId`, `ExtraArgs`/`ChoiceContext`/`Metadata`), exception rollback semantics, time non-determinism, decimal precision, and the top compile/runtime errors with fixes.
- **`references/upgrades.md`** — Smart Contract Upgrades: what's allowed and what isn't, V1/V2 package split, `deprecatedChoice`, runtime pitfalls, local verification.
- **`references/local-setup.md`** — installing the Daml SDK, every CLI command, the dev loop, sandbox vs Canton vs Splice localnet, common install errors.
- **`references/cheatsheet.md`** — copy-pasteable canonical patterns: full offer/accept with all four exits, `HoldingV1` impl, `TransferFactory` impl with `expectedAdmin` guard, subscription state machine, checked fetch, test skeleton, `daml.yaml`.
- **`scripts/ensure_refs.py`** — cross-platform (macOS/Linux/Windows) helper that ensures `canton`, `splice`, and `splice-wallet-kernel` are available locally, cloning them shallow into the OS cache on first use. Requires Python 3 and `git`.

## Install

### Via `npx skills`

```bash
npx skills add Swofty-Developments/daml-claude-skill
```

### Manually

```bash
git clone git@github.com:Swofty-Developments/daml-claude-skill.git ~/.claude/skills/daml
```

Then restart your Claude Code session. Claude will auto-load the skill when you're editing a `.daml` file, or you can invoke it directly with `/daml`.

## Install the Daml SDK (required for the verify loop)

The skill's `daml build && daml test` loop requires the Daml SDK:

```bash
# macOS / Linux
curl -sSL https://get.daml.com/ | sh -s -- --install-with-hash
export PATH="$HOME/.daml/bin:$PATH"
daml version
```

Splice pins SDK `3.3.0-snapshot.20250502.13767.0.v2fc6c7e2`. If you're working in a Splice subproject, `daml install project` from inside a package directory gets the right version.

## Contributing

PRs welcome — especially more file:line citations, additional edge cases, and corrections to any convention that has drifted from the upstream repos. When adding a new pattern, quote real Splice code rather than paraphrasing.

## License

MIT
