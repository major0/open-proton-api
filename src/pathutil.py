"""Path normalization utilities for API endpoint paths.

Normalizes path parameter naming across all extractors to follow
RESTful API conventions (https://restfulapi.net/resource-naming/):
- Path segments: lowercase nouns
- Path parameters: camelCase with consistent naming

This ensures that the same logical endpoint from different sources
(which may use shareId, shareID, ShareID, enc_shareID) all resolve
to the same directory in the api/ tree.
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
API_DIR = PROJECT_ROOT / "api"


# Known parameter name normalizations.
# Maps any variant we've seen to the canonical camelCase form.
_PARAM_CANONICAL: dict[str, str] = {
    # Share
    "shareid": "shareId",
    "enc_shareid": "shareId",
    "fromshareid": "fromShareId",
    "membershareid": "memberShareId",
    "usershareid": "userShareId",
    "vaultshareid": "vaultShareId",
    # Link
    "linkid": "linkId",
    "enc_linkid": "linkId",
    "parentlinkid": "parentLinkId",
    "albumlinkid": "albumLinkId",
    # Volume
    "volumeid": "volumeId",
    "enc_volumeid": "volumeId",
    "encryptedvolumeid": "volumeId",
    # Revision
    "revisionid": "revisionId",
    "enc_revisionid": "revisionId",
    # Device
    "deviceid": "deviceId",
    # Event
    "eventid": "eventId",
    # Message / Mail
    "messageid": "messageId",
    "draftid": "draftId",
    # Calendar
    "calendarid": "calendarId",
    "alarmid": "alarmId",
    "epochid": "epochId",
    "attendeeid": "attendeeId",
    "bookinguid": "bookingUid",
    # Contacts
    "contactid": "contactId",
    "contactemailid": "contactEmailId",
    # Address
    "addressid": "addressId",
    "enc_addressid": "addressId",
    "addressdid": "addressId",
    # User / Auth
    "authuid": "authUid",
    "uid": "uid",
    # Keys
    "keyid": "keyId",
    "userkeyid": "userKeyId",
    "tokenid": "tokenId",
    # Labels
    "labelid": "labelId",
    "enc_labelid": "labelId",
    "startlabelid": "startLabelId",
    # Members
    "memberid": "memberId",
    "enc_memberid": "memberId",
    "sharememberid": "shareMemberId",
    "groupmemberid": "groupMemberId",
    "group_member_enc_id": "groupMemberId",
    # Groups
    "groupid": "groupId",
    "group_enc_id": "groupId",
    "groupencid": "groupId",
    "groupinvitetoken": "groupInviteToken",
    # Filter / Domain
    "filterid": "filterId",
    "domainid": "domainId",
    # Attachments
    "attachmentid": "attachmentId",
    # Conversations
    "conversationid": "conversationId",
    # Folders
    "folderid": "folderId",
    # Files
    "fileid": "fileId",
    # Subscription
    "subscriptionid": "subscriptionId",
    # Invitations
    "invitationid": "invitationId",
    "inviteid": "inviteId",
    "externalinvitationid": "externalInvitationId",
    # Share URL
    "shareurlid": "shareUrlId",
    # Secure link
    "securelinkid": "secureLinkId",
    # Notification
    "notificationid": "notificationId",
    # Organization
    "orgincomingdefaultid": "orgIncomingDefaultId",
    "incomingdefaultid": "incomingDefaultId",
    # Credential
    "credentialid": "credentialId",
    # Mailbox
    "mailboxid": "mailboxId",
    # Node
    "nodeid": "nodeId",
    # Misc
    "urlid": "urlId",
    "clientid": "clientId",
    "client_id": "clientId",
    "itemid": "itemId",
    "slotid": "slotId",
    "chunkid": "chunkId",
    "ticketid": "ticketId",
    "logoid": "logoId",
    "logo_id": "logoId",
    "emailid": "emailId",
    "sharedid": "sharedId",
    "lasteventid": "lastEventId",
    "checklistid": "checklistId",
    "shareurl_id": "shareUrlId",
    "form_id": "formId",
    "portal_id": "portalId",
    "organization_id": "organizationId",
    "mspid": "mspId",
    # Generic
    "enc_id": "id",
    "id": "id",
}


def normalize_param_name(param: str) -> str:
    """Normalize a path parameter name to canonical camelCase form.

    Handles: shareID, ShareID, enc_shareID, shareId → shareId
    """
    # Strip braces if present
    raw = param.strip("{}")

    # Lookup by lowercase
    key = raw.lower()
    if key in _PARAM_CANONICAL:
        return _PARAM_CANONICAL[key]

    # If not in map, apply generic normalization:
    # strip enc_ prefix, convert trailing ID to Id
    normalized = raw
    normalized = normalized.removeprefix("enc_")

    # Convert trailing ID (uppercase) to Id
    if normalized.endswith("ID") and len(normalized) > 2:
        normalized = normalized[:-2] + "Id"

    # Ensure first char is lowercase (camelCase)
    if normalized and normalized[0].isupper():
        normalized = normalized[0].lower() + normalized[1:]

    return normalized


def normalize_path(path: str) -> str:
    """Normalize an API path to canonical form.

    - Ensures leading slash
    - Strips trailing slash
    - Normalizes all {paramName} to canonical camelCase
    - Resolves known version placeholders to concrete versions
    - Strips query strings
    """
    # Strip query strings
    path = path.split("?")[0]

    # Ensure leading slash
    if not path.startswith("/"):
        path = "/" + path

    # Strip trailing slash
    path = path.rstrip("/")

    # Resolve version placeholders to concrete versions
    # The TS SDK uses {_version} but all endpoints are actually v4
    path = path.replace("{_version}", "v4")

    # Normalize each path parameter
    def replace_param(m: re.Match) -> str:
        param = m.group(1)
        canonical = normalize_param_name(param)
        return "{" + canonical + "}"

    path = re.sub(r"\{([^}]+)\}", replace_param, path)

    # Normalize positional parameter aliases
    # albumLinkId at album child position is just linkId
    path = re.sub(r"/albums/\{albumLinkId\}", "/albums/{linkId}", path)
    # parentLinkId in folder context is just linkId
    path = re.sub(r"/folders/\{parentLinkId\}", "/folders/{linkId}", path)

    # Resolve generic {id} to context-specific names based on parent collection
    path = re.sub(r"/addresses/\{id\}", "/addresses/{addressId}", path)
    path = re.sub(r"/labels/\{id\}", "/labels/{labelId}", path)
    path = re.sub(r"/members/\{id\}", "/members/{memberId}", path)
    path = re.sub(r"/groups/\{id\}", "/groups/{groupId}", path)
    path = re.sub(r"/contacts/\{id\}", "/contacts/{contactId}", path)
    path = re.sub(r"/features/\{id\}", "/features/{featureCode}", path)
    path = re.sub(r"/features/\{featureId\}", "/features/{featureCode}", path)
    path = re.sub(r"/features/\{code\}", "/features/{featureCode}", path)
    path = re.sub(r"/keys/\{id\}", "/keys/{keyId}", path)
    path = re.sub(r"/events/\{id\}", "/events/{eventId}", path)
    path = re.sub(r"/sessions/\{id\}", "/sessions/{sessionId}", path)
    path = re.sub(r"/sessions/\{authUid\}", "/sessions/{uid}", path)
    path = re.sub(r"/devices/\{id\}", "/devices/{deviceId}", path)
    path = re.sub(r"/domains/\{id\}", "/domains/{domainId}", path)
    path = re.sub(r"/invitations/\{id\}", "/invitations/{invitationId}", path)
    path = re.sub(r"/volumes/\{id\}", "/volumes/{volumeId}", path)
    path = re.sub(r"/shares/\{id\}", "/shares/{shareId}", path)
    path = re.sub(r"/links/\{id\}", "/links/{linkId}", path)
    path = re.sub(r"/messages/\{id\}", "/messages/{messageId}", path)
    path = re.sub(r"/messages/\{draftId\}", "/messages/{messageId}", path)
    path = re.sub(r"/calendars/\{id\}", "/calendars/{calendarId}", path)
    path = re.sub(r"/notifications/\{id\}", "/notifications/{notificationId}", path)

    # Keys/user context
    path = re.sub(r"/keys/user/\{id\}", "/keys/user/{userKeyId}", path)

    # Filters
    path = re.sub(r"/filters/\{id\}", "/filters/{filterId}", path)

    # SAML configs — {uid} is the same config ID
    path = re.sub(r"/saml/configs/\{uid\}", "/saml/configs/{id}", path)

    # Organizations logo
    path = re.sub(r"/organizations/logo/\{id\}", "/organizations/logo/{logoId}", path)

    # Group members — memberId and groupMemberId are the same resource
    path = re.sub(r"/groups/members/\{memberId\}", "/groups/members/{groupMemberId}", path)
    # Groups owners — {id} is the same as specific param
    path = re.sub(r"/groups/owners/accept/\{id\}", "/groups/owners/accept/{inviteId}", path)
    path = re.sub(r"/groups/owners/add/\{id\}", "/groups/owners/add/{groupMemberId}", path)

    # Drive share URLs
    path = re.sub(r"/urls/\{urlId\}", "/urls/{shareUrlId}", path)

    # Drive external invitations — invitationId and externalInvitationId are same
    path = re.sub(
        r"/external-invitations/\{externalInvitationId\}",
        "/external-invitations/{invitationId}",
        path,
    )

    # Drive share members
    path = re.sub(
        r"/v2/shares/\{shareId\}/members/\{shareMemberId\}",
        "/v2/shares/{shareId}/members/{memberId}",
        path,
    )

    # Pass — sharedId and fromShareId are just shareId
    path = re.sub(r"/pass/v1/share/\{sharedId\}", "/pass/v1/share/{shareId}", path)
    path = re.sub(r"/pass/v1/share/\{fromShareId\}", "/pass/v1/share/{shareId}", path)

    # Pass vault — vaultShareId is just shareId
    path = re.sub(r"/pass/v1/vault/\{vaultShareId\}", "/pass/v1/vault/{shareId}", path)

    # Pass breach custom email
    path = re.sub(r"/breach/custom_email/\{emailId\}", "/breach/custom_email/{customEmailId}", path)

    # Pass invite group token
    path = re.sub(r"/invite/group/\{groupInviteToken\}", "/invite/group/{inviteToken}", path)

    # Members invitations — memberId at this position is invitationId
    path = re.sub(
        r"/members/invitations/\{memberId\}",
        "/members/invitations/{invitationId}",
        path,
    )

    # Malformed params from extractors
    path = re.sub(r"\{data\.JWT\}", "{jwt}", path)

    # Share URL context — generic {id} is shareUrlId
    path = re.sub(r"/urls/\{shareId\}/\{id\}", "/urls/{shareId}/{shareUrlId}", path)

    return path


def is_valid_path(path: str) -> bool:
    """Check if a normalized path is a valid API endpoint.

    Rejects paths that are clearly extraction errors (dynamic URLs,
    malformed parameters, etc.).
    """
    # Must start with a known service prefix
    if not path.startswith("/"):
        return False
    # Reject paths where the first segment is a parameter (dynamic URLs)
    first_segment = path.lstrip("/").split("/")[0]
    if first_segment.startswith("{"):
        return False
    # Reject paths with obviously malformed params
    return (
        "(" not in path and ")" not in path and "." not in path.split("/")[-1].replace(".json", "")
    )


def path_to_dir(path: str, api_dir: Path) -> Path:
    """Convert a normalized API path to a directory under api_dir."""
    parts = path.lstrip("/").split("/")
    return api_dir / "/".join(parts)


def extract_path_params(path: str) -> dict[str, dict]:
    """Extract path parameters from a normalized path."""
    params = {}
    for m in re.finditer(r"\{(\w+)\}", path):
        params[m.group(1)] = {"type": "string"}
    return params


def write_endpoint(path: str, operations: dict, source_name: str) -> None:
    """Normalize path, build endpoint dict, and write to the api/ tree.

    This is the single entry point all extractors should use for output.
    It ensures consistent path normalization and directory structure.
    Skips invalid/malformed paths silently.
    Strips operationId (provenance noise) and empty type-name-only fields
    (e.g. {"SomeType": {"type": "object"}} with no nested field detail).
    """
    normalized = normalize_path(path)
    if not is_valid_path(normalized):
        return

    # Strip operationId and clean operations
    cleaned_ops = {}
    for method, op_data in operations.items():
        cleaned = {}
        for k, v in op_data.items():
            if k == "operationId":
                continue
            if k == "requestBody":
                fields = _strip_empty_fields(v.get("fields", {}))
                if fields:
                    cleaned["requestBody"] = {"contentType": "application/json", "fields": fields}
            elif k == "responses":
                cleaned_responses = {}
                for code, resp in v.items():
                    resp_fields = _strip_empty_fields(resp.get("fields", {}))
                    if resp_fields:
                        cleaned_responses[code] = {"fields": resp_fields}
                if cleaned_responses:
                    cleaned["responses"] = cleaned_responses
            elif k == "queryParams":
                if v:
                    cleaned["queryParams"] = v
            else:
                cleaned[k] = v
        cleaned_ops[method] = cleaned

    # Skip if no operation has any real content (just empty method stubs)
    has_content = any(cleaned_ops.values())
    if not has_content:
        return

    endpoint: dict = {"path": normalized, "operations": cleaned_ops}
    path_params = extract_path_params(normalized)
    if path_params:
        endpoint["pathParams"] = path_params

    output_dir = path_to_dir(normalized, API_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{source_name}.json"
    with open(output_file, "w") as f:
        json.dump(endpoint, f, indent=2)
        f.write("\n")


def _strip_empty_fields(fields: dict) -> dict:
    """Remove fields that are just type-name references with no real detail.

    A field like {"SomeResponse": {"type": "object"}} or
    {"SomeRequest": {"type": "object", "description": "See SomeRequest type"}}
    is just a type name — it tells us nothing about the actual schema.

    Keep fields that have: nested fields, enum values, or are primitive types
    with meaningful names (not just a type-name reference).
    """
    if not fields:
        return {}

    result = {}
    for name, schema in fields.items():
        if not isinstance(schema, dict):
            continue
        # Keep if it has nested fields (actual structure)
        if "fields" in schema:
            result[name] = schema
            continue
        # Keep if it has enum values
        if "enum" in schema:
            result[name] = schema
            continue
        # Keep primitive types (string, integer, number, boolean) — these are real
        field_type = schema.get("type", "")
        if field_type in ("string", "integer", "number", "boolean", "array"):
            # But skip if the field name looks like a type reference
            # (PascalCase ending in Response/Request/Dto)
            if _is_type_reference_name(name):
                continue
            result[name] = schema
            continue
        # type: "object" with no fields — this is just a type name, skip
        if field_type == "object" and "fields" not in schema:
            continue

    return result


def _is_type_reference_name(name: str) -> bool:
    """Check if a field name looks like a type reference rather than a real field.

    Type references: GetShareBootstrapResponse, CreateFileRequest, CodeResponse
    Real fields: Code, ShareID, CurrentRevisionID, Size, State
    """
    type_suffixes = ("Response", "Request", "Dto", "Data")
    return any(name.endswith(s) for s in type_suffixes) and name[0].isupper()
