# Demonstration

1. Start the API and built UI. Open the workspace with your local operator key.
2. Propose `purchase 2 WIDGET` in baseline mode. Show the quantity, available stock and resource version. Explain that a proposal does not execute.
3. Approve the exact change, select Browser Use, and run it. Open the confirmed receipt, event history and downloadable evidence.
4. Switch to the local model and ask to reserve one ROOM. Show the actual generation evidence before approving.
5. Run the browser fault test: `RUN_BROWSER_TESTS=1 python -m unittest discover -s tests -p test_browser.py -k sigkill -v`. It kills the actual Chromium process after the owned portal commits and before confirmation reaches the browser. Confirm a single inventory change and the recovered receipt.
6. Run `-k page_script` to demonstrate that page content cannot manufacture operator approval or change approved arguments.
7. Show both model evaluation profiles. The small Qwen3 model's default thinking output failed the bounded JSON contract; explicit non-thinking mode improved completion on these eight fixtures. An unsupported task still produced an unsafe proposal, which the approval oracle denied. Human review remains essential.

## Business case

Operations teams often automate a form successfully and still cannot establish whether a timeout occurred before or after submission. This workbench makes the business receipt, exact approval and recovery state visible in one place. The useful outcome is fewer duplicate submissions and a reviewable chain of evidence, rather than autonomous interaction with every website.

The deliberate tradeoffs are a narrow owned portal, a small typed action vocabulary, human approval for every write, serialized transactions and explicit uncertainty. Extend to a real application only when it exposes an authoritative receipt or idempotency interface. A generic browser screenshot alone cannot provide the same effect guarantee.
