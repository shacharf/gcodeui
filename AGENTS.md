# Repository Guidelines

## Project Structure & Module Organization
The toolkit is intentionally small: `gcodeui.py` holds the Tk-based UI, serial handling, and command bindings; edit it when altering runtime behavior. Device presets live in `config.yaml`; treat it as end-user editable data. Runtime dependencies are pinned in `requriements.txt` and the root directory also contains `README.md` for quick start details. Add any new modules under the root or a dedicated package directory and keep configuration and assets alongside the code that consumes them.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create a local environment before installing tools.
- `pip install -r requriements.txt`: install the Tk UI, serial, and logging dependencies; run it whenever dependencies change.
- `python gcodeui.py --cfg config.yaml`: launch the UI with the default configuration; use `--port` and `--baud` overrides during device trials.

## Coding Style & Naming Conventions
Code is Python 3.7+ and formatted with `black`; run `black gcodeui.py` before submitting. Preserve 4-space indentation and keep lines under 100 characters. Use `snake_case` for functions and variables, `CapWords` for classes, and uppercase constants when adding shared configuration. Follow the existing logging pattern (`structlog.get_logger()`) and prefer small helper functions over inline lambdas for reusable behavior.

## Testing Guidelines
There is no automated test suite yet; validate changes by running `python gcodeui.py` against a real or mocked serial device. When introducing logic-heavy changes, add unit tests under a future `tests/` directory using `pytest`, and document any required fixtures or hardware simulators. Describe manual testing steps in the pull request when hardware interaction is required.

## Commit & Pull Request Guidelines
Keep commits focused, using short imperative messages (`Add serial retry`, `Update config docs`) similar to the existing history. Reference related issues in the body when available. Pull requests should include: concise summary of user-facing changes, noted config schema updates, screenshots or terminal captures when UI output changes, and verification notes (commands run, hardware used). Request review before merging and confirm the app launches without regression.

## Configuration Tips
Ship safe defaults in `config.yaml` and highlight any breaking changes in the changelog. When adding preset commands, include descriptive `title` labels and optional `color` values to maintain UI clarity, and remind users to secure their serial ports before deployment.
