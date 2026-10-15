import os
import json
from flask import url_for
import iiifauth.terms

# some globals
APP_PATH = os.path.dirname(os.path.abspath(__file__))
MEDIA_ROOT = os.path.join(APP_PATH, 'media')
# Load in the configuration for all the media and their auth services
with open(os.path.join(APP_PATH, 'auth2_media_config.json'), encoding='utf-8') as auth_config_file:
    MEDIA_AUTH_CONFIG = json.load(auth_config_file)
MEDIA_DICT = {file["file"]: file for file in MEDIA_AUTH_CONFIG["files"]}
# Manifests with more than one canvas, made from several of the files above
MANIFEST_DICT = {m["id"]: m for m in MEDIA_AUTH_CONFIG.get("manifests", [])}


def get_media_summaries():
    media_summaries = []
    for file in MEDIA_AUTH_CONFIG["files"]:
        resource = {
            "display": file["file"],
            "id": "tbc",
            "type": "tbc",
            "label": file["label"],
            "format": file["format"]
        }
        media_summaries.append(resource)
        if file["type"] == "Image" and file["provideImageService"]:
            # We won't assert services here, they'll be on the image service
            resource["type"] = "ImageService3"
            resource["id"] = url_for('image_id', identifier=file["file"], _external=True)
        else:
            # These are direct resources, so there's nowhere else to assert their auth services
            resource["type"] = file["type"]
            resource["id"] = url_for('resource_request', identifier=file["file"], _external=True)
            assert_auth_services(resource, file["file"], require_context=False)

        if file["provideManifest"]:
            resource["partOf"] = url_for('manifest', identifier=file["file"], _external=True)

    for summary in media_summaries:
        summary['label'] = replace_placeholders(summary['label'])

    return media_summaries


def get_manifest_summaries():
    """id and label of every Manifest this server provides, single-file ones first"""
    summaries = [{"identifier": file["file"], "label": file["label"]}
                 for file in MEDIA_AUTH_CONFIG["files"] if file["provideManifest"]]
    summaries += [{"identifier": m["id"], "label": m["label"]} for m in MANIFEST_DICT.values()]
    for summary in summaries:
        summary["id"] = url_for('manifest', identifier=summary["identifier"], _external=True)
        summary["label"] = replace_placeholders(summary["label"])
    return summaries


def replace_placeholders(label):
    # Some labels have URL placeholders:
    return label.replace('{server}', url_for('index', _external=True))


def get_auth_service_configs(config):
    """
        The auth service configurations for a file. A file can borrow the
        configuration in the "shared" section of the config with the hint "use_shared".
    """
    service_configurations = config.get('auth_services', [])
    if any(s.get("hint", None) == "use_shared" for s in service_configurations):
        return MEDIA_AUTH_CONFIG["shared"]["auth_services"]
    return service_configurations


def assert_auth_services(resource, identifier, require_context=True, context_carrier=None):
    """
        Augment the info.json, or other resource, with auth service(s) from our 'database' of auth policy
    """

    config = MEDIA_DICT[identifier]

    if context_carrier is None:
        context_carrier = resource

    current_context = context_carrier.get("@context", [])
    contexts = [current_context] if not isinstance(current_context, list) else current_context

    # although maxWidth is not really auth, this is a good place to add it.
    max_width = config.get('maxWidth', None)
    if max_width is not None and iiifauth.terms.CONTEXT_IMAGE_3 in contexts:
        resource['maxWidth'] = max_width

    service_configurations = get_auth_service_configs(config)
    if len(service_configurations) == 0:
        return

    # Add the auth context, if not already present
    if iiifauth.terms.CONTEXT_AUTH_2 not in contexts:
        contexts.insert(0, iiifauth.terms.CONTEXT_AUTH_2)

    # Add in the probe service as the immediate child service of the resource.
    # In this demo, each resource has its own probe service, 1:1
    # ... but some probe services have more than one access service, 1:*

    # TODO: define errorHeading and errorNote and make use of them in the demo
    # (these fields are also on the token service. Both probe and token can return message strings).
    probe_service = {
        "id": url_for('probe', identifier=identifier, _external=True),
        "type": "AuthProbeService2",
        "service": []
    }

    resource_services = resource.get("service", [])
    if not isinstance(resource_services, list):
        resource_services = [resource_services]
    resource_services.append(probe_service)
    resource["service"] = resource_services

    identifier_slug = 'shared' if config.get('shared', False) else identifier

    for service_config in service_configurations:
        pattern = get_pattern_name(service_config)
        # build new auth service here
        auth2_service = {
            "id": url_for('access_service', pattern=pattern, identifier=identifier_slug, _external=True),
            "type": "AuthAccessService2",
            "profile": service_config["profile"],
            "service": [
                {
                    "id": url_for('token_service', pattern=pattern, identifier=identifier_slug, _external=True),
                    "type": "AuthAccessTokenService2"
                },
                {
                    "id": url_for('logout_service', pattern=pattern, identifier=identifier_slug, _external=True),
                    "type": "AuthLogoutService2",
                    "label": {"en": ["Log out"]}
                }
            ]
        }
        # set display strings on the access service and its token service
        set_labels(service_config, auth2_service, ["label", "heading", "note", "confirmLabel"])
        set_labels(service_config, auth2_service["service"][0], ["errorHeading", "errorNote"])
        probe_service["service"].append(auth2_service)

    if require_context:
        context_carrier["@context"] = contexts


def get_pattern_name(service_config):
    pattern = service_config["profile"]
    # We use the profile to route to different UIs, but now there's no explicit clickthrough in the spec
    # As far as clients are concerned there is no difference between login, clickthrough or any other
    # form of "active". The difference between the interaction patterns "clickthrough" and "login"
    # is an application implementation detail, not a spec concern.

    hint = service_config.get("hint", None)
    if "clickthrough" == hint:
        pattern = "active-clickthrough"
    if "robot" == hint:
        pattern = "active-robot"
    if "5mins" == hint:
        pattern = "external-5mins"
    if pattern == "active":
        pattern = "active-login"
    return pattern


def set_labels(source, dest, labels):
    for label in labels:
        source_str = source.get(label, None)
        if source_str:
            dest[label] = lang_map(source_str)


def lang_map(s, lang="en"):
    return {lang: [s]}


def get_media_path(identifier):
    """Resolves a iiif identifier to the resource's path on disk."""
    return os.path.join(MEDIA_ROOT, identifier)


def get_all_files():
    return MEDIA_AUTH_CONFIG["files"]


def get_single_file(identifier):
    return MEDIA_DICT.get(identifier, None)


def make_manifest(identifier):
    """
        A IIIF Presentation 3 Manifest - either for a single file, or for one of the
        multi-canvas manifests in the "manifests" section of the config.
    """
    multi = MANIFEST_DICT.get(identifier, None)
    if multi:
        files = [MEDIA_DICT[f] for f in multi["files"]]
        source = multi
    else:
        file = MEDIA_DICT.get(identifier, None)
        if not file or not file["provideManifest"]:
            return None
        files = [file]
        source = file

    manifest = {
        "@context": iiifauth.terms.CONTEXT_PRESENTATION_3,
        "id": url_for('manifest', identifier=identifier, _external=True),
        "type": "Manifest",
        "label": lang_map(replace_placeholders(source["label"]))
    }

    metadata = source.get("metadata", [])
    if len(metadata) > 0:
        manifest["metadata"] = []
        for pair in metadata:
            manifest["metadata"].append({
                "label": lang_map(pair["label"]),
                "value": lang_map(replace_placeholders(pair["value"])),
            })
    for prop in ["summary", "requiredStatement"]:
        if prop in source:
            manifest[prop] = make_lang_maps(source[prop])
    if "rights" in source:
        manifest["rights"] = source["rights"]

    manifest["items"] = [make_canvas(file, manifest) for file in files]
    return manifest


def make_lang_maps(value):
    """A string becomes a language map; {"label": .., "value": ..} becomes a pair of them"""
    if isinstance(value, str):
        return lang_map(value)
    return {k: lang_map(v) for k, v in value.items()}


def make_canvas(file, manifest):
    """A Canvas for a single file. The manifest carries the @context for any auth services."""
    identifier = file["file"]
    root = url_for('index', _external=True)
    canvas_id = f"{root}canvases/{identifier}"
    body = {
        "id": "tbc",
        "type": file["type"],
        "format": file["format"]
    }
    canvas = {
        "id": canvas_id,
        "type": "Canvas",
        "label": lang_map(replace_placeholders(file["label"])),
        "items": [
            {
                "id": f"{root}annopages/{identifier}",
                "type": "AnnotationPage",
                "items": [
                    {
                        "id": f"{root}annotations/{identifier}",
                        "type": "Annotation",
                        "motivation": "painting",
                        "body": body,
                        "target": canvas_id
                    }
                ]
            }
        ]
    }

    has_dimensions = set_dimensions(file, canvas)
    set_dimensions(file, body)

    # TODO: assert auth services for the static image too even when it has an image service.
    if file["type"] == "Image" and file["provideImageService"]:
        # We won't assert AUTH services here, they'll be on the image service
        # We could put the auth service here too if we really wanted to, but we're
        # demonstrating the difference between having them in the Manifest and in the service (or maybe, probe)
        image_service = url_for('image_id', identifier=identifier, _external=True)
        body["id"] = f"{image_service}/full/max/0/default.jpg"
        body["service"] = [
            {
                "id": image_service,
                "type": "ImageService3",
                "profile": "level2"
            }
        ]
    elif has_dimensions:
        # This is a resource to be requested directly
        body["id"] = url_for('resource_request', identifier=identifier, _external=True)
        assert_auth_services(body, identifier, context_carrier=manifest)
    else:
        # This resource can't be painted on a canvas (e.g., a PDF or a 3D model).
        # Link the access-controlled resource from the Canvas's rendering property,
        # and paint a placeholder image on the canvas.
        canvas["rendering"] = [
            {
                "id": url_for('resource_request', identifier=identifier, _external=True),
                "type": body["type"],
                "label": canvas["label"],
                "format": body["format"]
            }
        ]
        assert_auth_services(canvas["rendering"][0], identifier, context_carrier=manifest)
        body["id"] = url_for('static', filename='placeholder.png', _external=True)
        body["type"] = "Image"
        body["format"] = "image/png"
        placeholder_dimensions = {"width": 800, "height": 600}
        set_dimensions(placeholder_dimensions, canvas)
        set_dimensions(placeholder_dimensions, body)

    return canvas


def set_dimensions(source, dest):
    # Clear any existing dimensions
    dest.pop("width", None)
    dest.pop("height", None)
    dest.pop("duration", None)
    has_dimensions = False
    width = source.get("width", None)
    height = source.get("height", None)
    duration = source.get("duration", None)
    if width:
        dest["width"] = width
        has_dimensions = True
    if height:
        dest["height"] = height
        has_dimensions = True
    if duration:
        dest["duration"] = duration
        has_dimensions = True

    return has_dimensions
