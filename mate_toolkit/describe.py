"""describe: attach typed, schema-aware metadata to a sub-component of the crate.

Two stages: `build` scans the folder into the manifest (a Dataset entity); `describe` fills it
in. The crate is the single source of truth, so this writes straight into ro-crate-metadata.json;
build-as-merge preserves it.

Schema semantics come from the profile's `component_types`: pick a `--type` and the profile knows
that type's curated fields (schema.org / CodeMeta) and prompts. The escape hatch is `--set
<property>=<value>` — any schema.org property, so nothing is boxed in.

  mate describe model_code_inputs/ --type SoftwareSourceCode \\
      --set programmingLanguage=Python --set buildInstructions=build.sh
"""
import json
from pathlib import Path

from .build_crate import build_crate
from .profile import load_profile


def describe(repo_dir, target, type_=None, name=None, description=None, sets=None, list_fields=False):
    repo_dir = Path(repo_dir).resolve()
    profile = load_profile(repo_dir)
    field_defs = ((profile.get("component_types", {}) or {}).get(type_, {}) or {}).get("fields", {}) if type_ else {}

    if list_fields:
        types = profile.get("component_types", {}) or {}
        if type_:
            return {"type": type_, "fields": {k: v.get("label", k) for k, v in field_defs.items()}}
        return {"types": {k: v.get("label", k) for k, v in types.items()}}

    crate_path = repo_dir / "ro-crate-metadata.json"
    build_crate(repo_dir, out_path=str(crate_path), merge=True)   # ensure the entity exists
    doc = json.loads(crate_path.read_text())

    tid = target if target.endswith("/") else target + "/"
    entity = next((e for e in doc["@graph"] if e.get("@id") == tid), None)
    if entity is None:
        return {"error": f"no dataset '{tid}' in the crate — is it a directory in the repo?"}

    applied, warnings = [], []
    if name:
        entity["name"] = name; applied.append("name")
    if description:
        entity["description"] = description; applied.append("description")
    if type_:
        cur = entity.get("@type", "Dataset")
        cur = [cur] if isinstance(cur, str) else list(cur)
        if type_ not in cur:
            cur.append(type_)
        entity["@type"] = cur; applied.append("@type")

    for kv in (sets or []):
        key, _, val = kv.partition("=")
        key, val = key.strip(), val.strip()
        if not key:
            continue
        if field_defs.get(key, {}).get("input") == "list":
            entity[key] = [x.strip() for x in val.split(",") if x.strip()]
        else:
            entity[key] = val
        applied.append(key)
        if type_ and field_defs and key not in field_defs:
            warnings.append(f"`{key}` is not a curated field for {type_} (allowed, but check the term)")

    crate_path.write_text(json.dumps(doc, indent=2))
    return {"described": tid, "type": type_, "set": applied,
            "curated_fields": list(field_defs), "warnings": warnings}
