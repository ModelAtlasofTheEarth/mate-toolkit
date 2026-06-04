"""from-issue: apply a submitted GitHub edit-entity issue-form to the crate.

The issue form is a generic ENTITY editor (target defaults to the root). Its answers become an
edit-intent — `(path, @type, {property: value})` — applied through the SAME `edit_entity` the
CLI uses, so the issue, the CLI, and Crate-O can't drift. Root-only references (a publication
citation, an external data payload) are handled as a post-pass, since they materialise contextual
/ external entities rather than set a plain property.

The issue is create/edit-time capture only; the crate is authoritative thereafter. The mapping
is drift-free: the form generator and this parser share `issue_form.form_spec`.
"""
import json
import re
from pathlib import Path

from .build_crate import _root_entity
from .describe import edit_entity, command_for
from .issue_form import form_spec, _ROOT_OPT, _TYPE_KEEP
from .payload import _adapter
from .profile import load_profile

_HEAD = re.compile(r"^###\s+(?P<label>.+?)\s*$", re.M)
_EMPTY = ("", "_No response_", "_no response_")


def parse_issue_body(body):
    """GitHub renders an issue-form submission as '### <label>\\n\\n<value>'. Return {label: value}."""
    out = {}
    heads = list(_HEAD.finditer(body or ""))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        out[m.group("label").strip()] = body[m.end():end].strip()
    return out


def apply_issue(repo_dir, body, out_path=None):
    repo_dir = Path(repo_dir).resolve()
    profile = load_profile(repo_dir)
    parsed = parse_issue_body(body)
    specs = {s["label"]: s for s in form_spec(profile)}   # labels are stable regardless of dirs

    target, type_ = ".", None
    name = description = publication = None
    authors, sets = [], []
    backend = ref = None

    for label, spec in specs.items():
        val = parsed.get(label, "")
        if val in _EMPTY:
            continue
        role = spec.get("role")
        if role == "path":
            target = "." if val in (_ROOT_OPT, "(root)") else val.strip()
        elif role == "type":
            type_ = None if val == _TYPE_KEEP else val.strip()
        elif spec.get("target") == "payload":
            if spec["id"] == "payload_backend":
                backend = val
            else:
                ref = val
        elif spec.get("enrich") == "publication":
            publication = val
        else:
            prop, inp = spec["property"], spec["input"]
            if inp == "people":
                authors = [line for line in val.splitlines() if line.strip()]
            elif prop == "name":
                name = val
            elif prop == "description":
                description = val
            elif inp == "dropdown" and prop == "license" and val == "(other URL)":
                continue
            else:
                sets.append(f"{prop}={val}")   # edit_entity shapes lists/license by the field def

    # 1) the universal edit, via the shared editor (same code path as the CLI)
    result = edit_entity(repo_dir, target, type_=type_, name=name, description=description,
                         authors=authors or None, sets=sets or None)
    if result.get("error"):
        return result
    tid = result.get("edited")
    applied = list(result.get("applied", []))

    # 2) root-only references (citation, external payload) — they create/link other entities
    crate_path = Path(out_path) if out_path else repo_dir / "ro-crate-metadata.json"
    doc = json.loads(crate_path.read_text())
    root = _root_entity(doc)
    if tid == "./":
        if publication:
            root["citation"] = {"@id": publication if publication.startswith("http")
                                else f"https://doi.org/{publication}"}
            applied.append("citation")
        if backend and backend not in ("(none)", "") and ref:
            ent, backing, _ = _adapter({"backend": backend,
                                        ("record" if backend == "zenodo" else "url"): ref})
            if ent["@id"]:
                ent["about"] = {"@id": backing}
                doc["@graph"] = [e for e in doc["@graph"] if e.get("additionalType") != "ExternalPayload"]
                doc["@graph"].append(ent)
                for e in doc["@graph"]:
                    if e.get("@id") == "./":
                        e.setdefault("hasPart", []).append({"@id": ent["@id"]})
                applied.append("payload")
        crate_path.write_text(json.dumps(doc, indent=2))

    command = command_for(target, type_, name, description, authors, sets)
    return {"applied": applied, "edited": tid, "command": command, "out": str(crate_path)}
