"""validate: red/green check that a repo's crate is well-formed enough to be a M@TE model.

MVP rules (hard-coded). Later these come from the pack profile's `requires_for_website`
(TARGET_ARCHITECTURE.md §6c/§7): render is permissive, the validator is the gate.
"""
from pathlib import Path

from .build_crate import build_crate

# minimal required root properties for a valid model
REQUIRED_ROOT = ["name", "license", "creator"]


def validate(repo_dir, reverse_engineer=False):
    """Return (errors, warnings). Empty errors == valid."""
    repo_dir = Path(repo_dir)
    doc, _ = build_crate(repo_dir, out_path=None, reverse_engineer=reverse_engineer)
    graph = doc["@graph"]
    by_id = {e.get("@id"): e for e in graph}
    root = by_id.get("./", {})

    errors, warnings = [], []

    for prop in REQUIRED_ROOT:
        val = root.get(prop)
        if not val:
            errors.append(f"root entity is missing required property `{prop}`")

    # every local File entity must point at a file that exists on disk
    for e in graph:
        if e.get("@type") != "File":
            continue
        i = e.get("@id", "")
        if not i or i.startswith(("http", "#", "./")):
            continue
        if not (repo_dir / i).exists():
            errors.append(f"crate references missing local file `{i}`")

    # soft checks
    if not root.get("description"):
        warnings.append("root entity has no description")
    if not any(e.get("additionalType") == "ExternalPayload" for e in graph) \
            and not by_id.get("model_output_data/"):
        warnings.append("no model output data (local dir or external payload) found")

    return errors, warnings
