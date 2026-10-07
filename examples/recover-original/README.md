# Recover the original

From the root, run `python3 tools/quickstart.py`. It builds/installs both
packages into temporary environments and runs the examples against separate
local synthetic sessions. It verifies original lookup causes zero redispatches.

Fixed operation IDs are permitted only for this fixture. In an integration,
persist your own operation ID and intended request before dispatch. An
uncertain reply does not justify generating a new identity.

The examples inject closure and fresh approval. No kernel, native provider or
customer workflow is exercised. Use `--output ./example-output` to retain
synthetic result JSON, without the session API key.
