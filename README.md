# Browser Agent Workbench

An operations workspace for purchase requisitions, reservations, and inventory adjustments. Browser actions require exact human approval and produce durable application receipts. If a browser loses its response after submission, the workbench reconciles the existing receipt instead of repeating the operation.

This is an owned local reference environment. It never purchases goods or signs into third-party accounts.

## Development

Requires Python 3.11+, Node 20+ and Chromium. Run `python3 -m unittest discover -s tests -v` for the core suite. Runtime and browser setup instructions are expanded alongside the implementation.
