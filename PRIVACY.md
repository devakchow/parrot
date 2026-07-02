# Privacy Policy

**Parrot** is a Claude Code plugin that runs entirely on your machine within
your Claude Code session.

- It collects no personal data.
- It includes no telemetry or analytics.
- It makes no network requests of its own and sends no data to the author or
  any third party.
- Its guard hook reads only the local tool-call metadata Claude Code passes to
  it (the acting agent's type and the target file path) to decide whether to
  block an edit. That data never leaves your machine.

Any code that Parrot's agents read, write, or execute is handled locally by
Claude Code under your own configuration and permissions, subject to
[Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) for
Claude Code itself.

Questions: open an issue at https://github.com/devakchow/parrot/issues
