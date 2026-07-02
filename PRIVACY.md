# Privacy Policy

**Parrot** is a Claude Code plugin that runs entirely on your machine within
your Claude Code session.

- It collects no personal data.
- It includes no telemetry or analytics.
- It makes no network requests of its own and sends no data to the author or
  any third party.
- Its guard hooks read only the local tool-call metadata Claude Code passes to
  them (the acting agent's type, target file paths, and shell command text) to
  decide whether to block an action. That data never leaves your machine.
- Loop state and run artifacts are written only to your local plugin-data
  directory and to `.parrot/` inside your project.
- **Oracle (opt-in, off by default):** if you enable the `oracle_enabled`
  setting and have a third-party model CLI installed (`codex` or `gemini`),
  parrot pipes a short, distilled question about the current failure (exact
  error text and what was ruled out — never your whole repository) to that
  CLI. That content is then handled under the third party's own privacy
  policy. Leave the setting off and parrot never invokes them.

Any code that Parrot's agents read, write, or execute is handled locally by
Claude Code under your own configuration and permissions, subject to
[Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) for
Claude Code itself.

Questions: open an issue at https://github.com/devakchow/parrot/issues
