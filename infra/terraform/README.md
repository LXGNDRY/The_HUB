# Durable worker infrastructure

This Terraform root is intentionally not auto-applied. It creates the least-privilege worker identity, Cloud Run Job, primary job topic, and dead-letter topic. Production rollout requires a reviewed plan, remote state, environment-specific variables, IAM bindings limited to required secrets/resources, and staging evidence.
