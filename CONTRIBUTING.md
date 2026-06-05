# Contributing

## Encoding

This repository uses UTF-8 as the default encoding.

- Source code, scripts, configuration, `.env`, JSON, and TOML files should be saved as UTF-8 without BOM.
- `README.md` may keep UTF-8 BOM when needed for compatibility with Windows Chinese editors.
- When adding new files, follow the rules in `.editorconfig`.

## Notes

- Do not introduce UTF-16, GBK, or platform-specific encodings into the repository.
- If a file already contains mojibake or legacy encoding artifacts, normalize it as a separate change when practical.
