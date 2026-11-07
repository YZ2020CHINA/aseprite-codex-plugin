# Third-party components and names

The MCP bridge, Lua extension, skill, packaging scripts and CLI adapter in this
repository are MIT licensed. This repository contains no aseprite-live source.

- **N7z/aseprite-live**: optional, separately installed application, AGPL-3.0-only.
  Source: https://github.com/N7z/aseprite-live
  Tested revision: `841fc81b519bd9d10f8ff9b29e43ea28e0c408f4`.
  The adapter launches its unmodified public CLI as a separate process and
  reads its announced URL. Do not remove the upstream license when distributing
  that application. The MIT license does not relicense aseprite-live.
- **diivi/aseprite-mcp**: architectural reference for Lua batch calls and previews.
  https://github.com/diivi/aseprite-mcp . No source code was copied from it.
- **Aseprite**: separately installed commercial software, not included here.
  Its names, trademarks and original icons belong to their respective owners.
  During local installation the builder copies `data/icons/ase256.png` from
  the user's Aseprite installation for the plugin icon. The icon is excluded
  from this repository and source ZIP; the MIT license does not cover it.

This is an independent integration, not an official Aseprite or OpenAI product.
