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
    - Strips query strings
    """
    # Strip query strings
    path = path.split("?")[0]

    # Ensure leading slash
    if not path.startswith("/"):
        path = "/" + path

    # Strip trailing slash
    path = path.rstrip("/")

    # Normalize each path parameter
    def replace_param(m: re.Match) -> str:
        param = m.group(1)
        canonical = normalize_param_name(param)
        return "{" + canonical + "}"

    path = re.sub(r"\{([^}]+)\}", replace_param, path)

    return path


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
    """
    normalized = normalize_path(path)
    endpoint: dict = {"path": normalized, "operations": operations}
    path_params = extract_path_params(normalized)
    if path_params:
        endpoint["pathParams"] = path_params

    output_dir = path_to_dir(normalized, API_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{source_name}.json"
    with open(output_file, "w") as f:
        json.dump(endpoint, f, indent=2)
        f.write("\n")
