# Verifier Stage

The first stage of the pipeline. Point a coding agent at [`CLAUDE.md`](./CLAUDE.md) and follow the workflow to generate the verifier (`<app>.py`, `README.md`, `Test.md`, `test_<app>.py`) for each target app.

Requires an [E2B](https://e2b.dev/) account — sandboxes are used to install the app and run verifier tests end-to-end. Put your `E2B_API_KEY` in `.env`.
