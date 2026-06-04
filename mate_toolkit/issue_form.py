"""Generate a GitHub issue form from the profile, and expose the SAME field spec the parser
uses — so the form, the issue→crate mapping, and validation can't drift. Field id == profile
field name, so `from_issue` maps each answer straight back to its schema.org `property`.
"""
import yaml

_PEOPLE_HELP = 'One per line: an ORCID iD (e.g. 0000-0002-1270-4377), or "Family, Given".'
_LIST_HELP = "Comma-separated."

# Generic fallbacks. A profile's `form:` block overrides any of these, so domain wording
# ("model", "M@TE") lives in the profile — never hardcoded in the engine.
_INTRO = ("Add or edit metadata for this dataset — or for one specific folder/file in it (pick it "
          "above; leave as the root for the dataset as a whole). On submit, an automated action "
          "writes your answers into the RO-Crate (`ro-crate-metadata.json`) — the single source of "
          "truth. **Edit the crate afterwards (CLI / Crate-O), not by reopening this issue.**")
_FORM_DEFAULTS = {
    "name": "Add / edit metadata",
    "description": "Add or edit metadata on an entity in the crate (defaults to the dataset root).",
    "title": "[edit] ",
    "labels": ["mate-edit"],
}


_ROOT_OPT = "(the dataset itself / root)"
_TYPE_KEEP = "(keep current)"


def form_spec(profile, dirs=None):
    """Ordered list of field specs shared by the form generator and the issue parser.

    The form is a generic ENTITY editor: a path selector (defaults to the root) + an optional
    type tag + the universal/root fields. `dirs` (live first-level folders, passed by the build
    workflow) populate the path dropdown; without them the path is a free-text input. This is a
    GitHub-surface concern, so it's a parameter — NOT something the profile knows about."""
    specs = []
    # entity selector: which thing to edit. "(root)" -> the dataset itself. The LABEL must be
    # identical whether it renders as a dropdown (form has live dirs) or a text box (parser, no
    # dirs) — the parser keys on labels, so they can't drift.
    if dirs:
        specs.append({"id": "path", "role": "path", "input": "dropdown", "required": False,
                      "label": "Which entity to edit", "options": [_ROOT_OPT] + list(dirs)})
    else:
        specs.append({"id": "path", "role": "path", "input": "text", "required": False,
                      "label": "Which entity to edit",
                      "help": "folder/file path; blank = the dataset root"})
    # optional type tag (type-SPECIFIC fields are edited in Crate-O, not here — static form)
    type_opts = [_TYPE_KEEP] + list((profile.get("component_types", {}) or {}).keys())
    if len(type_opts) > 1:
        specs.append({"id": "entity_type", "role": "type", "input": "dropdown", "required": False,
                      "label": "Type tag (optional — type-specific fields are edited in Crate-O)",
                      "options": type_opts})

    for name, fdef in (profile.get("root", {}) or {}).get("fields", {}).items():
        specs.append({
            "id": name, "label": fdef.get("label", name), "input": fdef.get("input", "text"),
            "property": fdef.get("property", name), "options": fdef.get("options"),
            "required": False,   # an EDIT form has no required fields (you may touch one entity)
            "enrich": fdef.get("enrich"), "target": "root",
        })
    payload = profile.get("payload", {}) or {}
    if payload.get("backends"):
        specs.append({"id": "payload_backend", "target": "payload", "input": "dropdown",
                      "label": "External data payload — backend (optional)",
                      "options": ["(none)"] + list(payload["backends"]), "required": False})
        specs.append({"id": "payload_ref", "target": "payload", "input": "input", "required": False,
                      "label": "Payload reference (e.g. Zenodo record id, or a URL)"})
    return specs


def _element(spec):
    inp = spec["input"]
    attrs = {"label": spec["label"]}
    if inp == "dropdown":
        etype = "dropdown"
        attrs["options"] = list(spec.get("options") or [])
    elif inp in ("textarea", "people"):
        etype = "textarea"
        if inp == "people":
            attrs["description"] = _PEOPLE_HELP
    elif inp == "list":
        etype = "input"
        attrs["description"] = _LIST_HELP
    else:
        etype = "input"
    element = {"type": etype, "id": spec["id"], "attributes": attrs}
    if etype in ("input", "textarea", "dropdown"):
        element["validations"] = {"required": bool(spec.get("required"))}
    return element


def build_issue_form(profile, dirs=None, title=None, labels=None, name=None, intro=None):
    """Build the GitHub edit-entity issue form. `dirs`/`title`/`labels` are GITHUB-SURFACE knobs
    (passed by the build workflow), kept OUT of the profile. `name`/`intro` are display text and
    may come from the profile's `form:` block, but a param overrides. The title prefix the
    workflow gates on lives here, not in the contract."""
    form = profile.get("form", {}) or {}
    intro = intro or form.get("intro", _INTRO)
    body = [{"type": "markdown", "attributes": {"value": intro}}]
    body += [_element(s) for s in form_spec(profile, dirs=dirs)]
    return {
        "name": name or form.get("name", _FORM_DEFAULTS["name"]),
        "description": form.get("description", _FORM_DEFAULTS["description"]),
        "title": title or _FORM_DEFAULTS["title"],          # GitHub gate prefix — surface, not profile
        "labels": labels or _FORM_DEFAULTS["labels"],
        "body": body,
    }


def write_issue_form(profile, out_path, dirs=None, title=None, labels=None):
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(build_issue_form(profile, dirs=dirs, title=title, labels=labels), f,
                       sort_keys=False, default_flow_style=False, allow_unicode=True)
    return out_path


# ── per-component-type "describe" forms (the chooser becomes the type-picker) ──

def component_form_spec(profile, type_):
    """Ordered specs for a describe-<type> form, shared by the generator and the parser."""
    fields = ((profile.get("component_types", {}) or {}).get(type_, {}) or {}).get("fields", {})
    specs = [
        {"id": "target", "role": "target", "input": "text", "required": True,
         "label": "Folder to describe (e.g. model_code_inputs/)"},
        {"id": "name", "property": "name", "input": "text", "label": "Name"},
        {"id": "description", "property": "description", "input": "textarea", "label": "Description"},
    ]
    for prop, fdef in fields.items():
        specs.append({"id": prop, "property": prop, "input": fdef.get("input", "text"),
                      "label": fdef.get("label", prop), "options": fdef.get("options")})
    return specs


def build_component_form(profile, type_):
    label = ((profile.get("component_types", {}) or {}).get(type_, {}) or {}).get("label", type_)
    body = [{"type": "markdown", "attributes": {"value": (
        f"Describe a **{label}** component. Give the folder and fill what you can — an action "
        "writes it into the crate (the single source of truth)."
    )}}]
    body += [_element(s) for s in component_form_spec(profile, type_)]
    return {
        "name": f"Describe: {label}",
        "description": f"Describe a {type_} component of this model",
        "title": f"[describe:{type_}] ",
        "labels": ["describe"],
        "body": body,
    }


def write_component_form(profile, type_, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(build_component_form(profile, type_), f, sort_keys=False,
                       default_flow_style=False, allow_unicode=True)
    return out_path
