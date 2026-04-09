# daml-claude-skill

A [Claude Code skill](https://code.claude.com/docs/en/skills) that teaches Claude to write production-quality [Daml](https://www.digitalasset.com/developers) on [Canton Network](https://canton.network/).

Built from the canonical reference corpus: [Hyperledger Splice](https://github.com/hyperledger-labs/splice), the [Canton platform](https://github.com/digital-asset/canton), and the [Splice Wallet Kernel](https://github.com/hyperledger-labs/splice-wallet-kernel). Every convention is grounded in a real file:line citation from those repos, and the skill auto-clones them on first use — no manual setup required.

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
