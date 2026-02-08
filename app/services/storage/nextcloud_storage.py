"""
Nextcloud storage utilities.

This module provides helper functions to upload, download, list and
generate public links for files stored in a Nextcloud instance via
WebDAV. The design is inspired by an equivalent implementation in a
Node.js environment, but rewritten for Python. All operations use
HTTP Basic authentication and standard WebDAV/OCS APIs exposed by
Nextcloud. The functions will determine credentials and base URLs
from Flask's application configuration (`NEXTCLOUD_URL`,
`NEXTCLOUD_USER`, `NEXTCLOUD_PASS`) or environment variables of the
same name when called outside of a Flask request or application
context. If any of these values are missing an exception will be
raised.

Functions:

* `upload_bytes(path: str, data: bytes, content_type: str) -> str`
  Uploads arbitrary bytes to the specified remote path relative to the
  user root. Intermediate directories will be created as needed.

* `download(path: str) -> bytes`
  Downloads the contents of a file from Nextcloud.

* `list_objects(prefix: str) -> list[dict]`
  Lists files under a given directory and returns a list of
  dictionaries containing at least the file name and path.

* `signed_url(path: str, expires_in: int | None = None) -> str`
  Creates a public share link for a file and returns a direct
  download URL. The `expires_in` parameter is ignored for now since
  Nextcloud's OCS API does not allow specifying expiry on link
  creation without additional parameters.

Note:
This module relies on the `requests` library and standard library
functions only. It avoids external dependencies such as a dedicated
WebDAV client to reduce the maintenance burden. Error handling is
kept simple—any unexpected status codes result in a `RuntimeError` or
`FileNotFoundError` where appropriate. Consumers should catch these
exceptions and translate them to API responses as needed.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import List, Dict, Tuple
from uuid import uuid4
from urllib.parse import quote, urlparse, urlunparse

import requests
from flask import current_app

# Set a maximum upload size (in bytes). Adjust as needed; here we
# enforce a 2 MB limit for uploaded files.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _sanitize_filename(filename: str) -> str:
    """Generate a safe filename by replacing invalid characters and
    appending a timestamp and a random suffix. This mirrors the
    behaviour of the previous storage helper to ensure unique filenames
    and avoid directory traversal vulnerabilities.

    Args:
        filename: The original filename provided by the caller.

    Returns:
        A sanitized, unique filename with its extension preserved.
    """
    if not filename:
        base, ext = "file", ""
    else:
        base, ext = os.path.splitext(filename)
    # Replace characters not allowed in filenames with underscore
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "file"
    # Keep only alphanumeric and dot characters in the extension
    ext = re.sub(r"[^A-Za-z0-9.]", "", ext)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:8]
    return f"{base}_{timestamp}_{suffix}{ext.lower()}"


def _assert_max_bytes(bytes_len: int) -> None:
    """Raise an error if the provided byte length exceeds the configured maximum."""
    if bytes_len is not None and bytes_len > MAX_UPLOAD_BYTES:
        raise ValueError(f"Ukuran file maksimal {MAX_UPLOAD_BYTES} bytes")


def _resolve_dav_base_url(raw: str, username: str) -> str:
    """Resolve a raw URL into a Nextcloud WebDAV base URL for the given user.

    Nextcloud supports multiple forms for WebDAV endpoints. For
    example, the user may supply a base instance URL, a `/remote.php/dav`
    root, or the full path including the user. This helper ensures
    that the returned URL always points to the WebDAV root for the
    specific user and ends with a trailing slash.

    Args:
        raw: The raw URL provided via config or environment.
        username: The Nextcloud username.

    Returns:
        A string containing the resolved WebDAV base URL ending with `/`.
    """
    if not raw or not username:
        raise ValueError("NEXTCLOUD_URL dan NEXTCLOUD_USER wajib ada")
    u = urlparse(str(raw).strip())
    p0 = u.path.rstrip("/")
    # If user provides /remote.php/webdav (legacy path)
    if p0.endswith("/remote.php/webdav"):
        new_path = f"{p0[:-len('/remote.php/webdav')]}/remote.php/dav/files/{quote(username)}"
        return urlunparse((u.scheme, u.netloc, new_path + "/", "", "", ""))
    # If already includes /remote.php/dav/files/
    if "/remote.php/dav/files/" in p0:
        return urlunparse((u.scheme, u.netloc, p0 + "/", "", "", ""))
    # If provides /remote.php/dav (without /files)
    if p0.endswith("/remote.php/dav"):
        new_path = f"{p0}/files/{quote(username)}"
        return urlunparse((u.scheme, u.netloc, new_path + "/", "", "", ""))
    # Otherwise treat as base instance URL
    new_path = f"{p0}/remote.php/dav/files/{quote(username)}"
    return urlunparse((u.scheme, u.netloc, new_path + "/", "", "", ""))


def _derive_instance_base_url(dav_base: str) -> str:
    """Derive the base instance URL from a DAV base URL.

    This strips the `/remote.php/dav/files/<user>` part so that OCS
    endpoints can be constructed correctly.

    Args:
        dav_base: The resolved DAV base URL.

    Returns:
        A string containing the instance base URL (no trailing slash).
    """
    u = urlparse(dav_base)
    parts = [p for p in u.path.split("/") if p]
    try:
        idx = parts.index("remote.php")
    except ValueError:
        return f"{u.scheme}://{u.netloc}"
    base_path = "/" + "/".join(parts[:idx])
    return f"{u.scheme}://{u.netloc}{base_path}"


def _get_credentials() -> Tuple[str, str, str, str]:
    """Retrieve Nextcloud credentials and derived URLs.

    Attempts to read the configuration from Flask's `current_app` if
    available, falling back to environment variables. It returns both
    the DAV base URL and the instance base URL, along with the
    username and password. A `RuntimeError` will be raised if any of
    the required values are missing.

    Returns:
        A tuple `(dav_base, instance_base, username, password)`.
    """
    url = None
    username = None
    password = None
    try:
        app = current_app._get_current_object()  # type: ignore[attr-defined]
        url = app.config.get("NEXTCLOUD_URL") or os.getenv("NEXTCLOUD_URL")
        username = app.config.get("NEXTCLOUD_USER") or os.getenv("NEXTCLOUD_USER")
        password = app.config.get("NEXTCLOUD_PASS") or os.getenv("NEXTCLOUD_PASS")
    except Exception:
        url = os.getenv("NEXTCLOUD_URL")
        username = os.getenv("NEXTCLOUD_USER")
        password = os.getenv("NEXTCLOUD_PASS")
    if not url or not username or not password:
        raise RuntimeError(
            "NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASS wajib di-set"
        )
    dav_base = _resolve_dav_base_url(url, username)
    instance_base = _derive_instance_base_url(dav_base)
    return dav_base, instance_base, username, password


def _ensure_dir(session: requests.Session, dav_base: str, remote_folder: str) -> None:
    """Ensure that a remote directory exists on the Nextcloud server.

    Splits the folder path and iteratively creates each level using
    `MKCOL`. If the directory already exists, a status code of 405
    (Method Not Allowed) is considered acceptable. Any other
    unexpected status codes will raise an exception.

    Args:
        session: A `requests.Session` with authentication set.
        dav_base: The DAV base URL ending with a slash.
        remote_folder: The directory path relative to the DAV base.
    """
    if not remote_folder:
        return
    segments = [seg for seg in remote_folder.strip("/").split("/") if seg]
    current = ""
    for seg in segments:
        current = f"{current}/{seg}" if current else seg
        url = dav_base + current
        # Check existence using a PROPFIND request with depth 0
        head = session.request("PROPFIND", url, headers={"Depth": "0"})
        if 200 <= head.status_code < 300:
            continue
        # Attempt to create directory
        mk = session.request("MKCOL", url)
        # 201 Created or 405 Method Not Allowed (already exists) are ok
        if mk.status_code not in (201, 405):
            raise RuntimeError(
                f"Failed to create directory '{current}' in Nextcloud (status {mk.status_code})"
            )


def upload_bytes(path: str, data: bytes, content_type: str) -> str:
    """Upload a binary blob to Nextcloud via WebDAV.

    The function automatically ensures that any intermediate
    directories in the provided `path` exist. It enforces a maximum
    upload size and raises an exception if exceeded.

    Args:
        path: Remote path relative to the user's root (e.g. "uploads/image.png").
        data: Byte content to be uploaded.
        content_type: MIME type of the content (e.g. "image/jpeg").

    Returns:
        The remote path at which the file was stored.
    """
    if not path:
        raise ValueError("path wajib diisi")
    if data is None:
        raise ValueError("data file wajib diisi")
    _assert_max_bytes(len(data))
    # Normalise path separators and remove leading/trailing slashes
    remote_path = path.replace("\\", "/").strip("/")
    # Retrieve credentials and base URLs
    dav_base, _, username, password = _get_credentials()
    # Derive folder
    parts = remote_path.split("/")
    folder = "/".join(parts[:-1])
    # Setup session
    session = requests.Session()
    session.auth = (username, password)
    # Ensure directory exists
    _ensure_dir(session, dav_base, folder)
    # Upload file using PUT
    url = dav_base + remote_path
    headers = {"Content-Type": content_type or "application/octet-stream"}
    resp = session.put(url, data=data, headers=headers)
    if 200 <= resp.status_code < 300:
        return remote_path
    raise RuntimeError(f"Gagal upload file ke Nextcloud (status {resp.status_code})")


def download(path: str) -> bytes:
    """Retrieve a file from Nextcloud.

    Args:
        path: Remote path relative to the user root.

    Returns:
        The raw bytes of the requested file.

    Raises:
        FileNotFoundError: If the file does not exist or the request fails.
    """
    if not path:
        raise ValueError("path wajib diisi")
    dav_base, _, username, password = _get_credentials()
    remote_path = path.replace("\\", "/").strip("/")
    url = dav_base + remote_path
    resp = requests.get(url, auth=(username, password))
    if 200 <= resp.status_code < 300:
        return resp.content
    raise FileNotFoundError(
        f"File '{path}' tidak ditemukan di Nextcloud (status {resp.status_code})"
    )


def list_objects(prefix: str) -> List[Dict[str, str]]:
    """List objects (files) under a directory in Nextcloud.

    This function issues a WebDAV `PROPFIND` request with `Depth: 1`
    and returns a list of dictionaries containing at least the name and
    path for each file. The directory itself is excluded from the
    results. Only the top-level children are returned (no recursive
    traversal).

    Args:
        prefix: The directory prefix relative to the user root.

    Returns:
        A list of dictionaries with `name` and `path` keys.
    """
    dav_base, _, username, password = _get_credentials()
    remote_prefix = prefix.replace("\\", "/").strip("/")
    url = dav_base + remote_prefix
    # WebDAV requires trailing slash to list directory
    if not url.endswith("/"):
        url = url + "/"
    headers = {"Depth": "1"}
    resp = requests.request("PROPFIND", url, auth=(username, password), headers=headers)
    # 207 Multi-Status indicates a successful PROPFIND response
    if resp.status_code not in (207, 200):
        raise RuntimeError(
            f"Gagal list objek di Nextcloud (status {resp.status_code})"
        )
    from xml.etree import ElementTree as ET
    tree = ET.fromstring(resp.content)
    ns = {"d": "DAV:"}
    items: List[Dict[str, str]] = []
    # Iterate over each <d:response> element
    for response in tree.findall("d:response", ns):
        href_elem = response.find("d:href", ns)
        if href_elem is None or not href_elem.text:
            continue
        href = href_elem.text
        # Skip the directory itself
        # Remove any trailing slash and leading slash from href
        from urllib.parse import unquote
        decoded = unquote(href)
        if decoded.endswith("/"):
            decoded = decoded[:-1]
        if decoded.startswith("/"):
            decoded = decoded[1:]
        # Remove the DAV base path (domain and path) leaving only the relative
        dav_path = urlparse(dav_base).path.strip("/")
        idx = decoded.find(dav_path)
        if idx >= 0:
            relative_path = decoded[idx + len(dav_path):].lstrip("/")
        else:
            relative_path = decoded
        # Exclude the directory itself
        if relative_path.rstrip("/") == remote_prefix:
            continue
        # Only return immediate children (depth 1); deeper levels will
        # include a slash inside relative_path beyond remote_prefix
        if "/" in relative_path[len(remote_prefix):].strip("/"):
            continue
        name = relative_path.split("/")[-1]
        items.append({"name": name, "path": relative_path})
    return items


def signed_url(path: str, expires_in: int | None = None) -> str:
    """Create a public share link for a file on Nextcloud.

    This helper wraps Nextcloud's OCS API (Open Collaboration Services)
    to create a public link. Only read-only links are created by
    default. The `expires_in` parameter is reserved for future use and
    currently ignored.

    Args:
        path: Remote path of the file relative to the user root.
        expires_in: Optional expiration time in seconds (unused).

    Returns:
        A direct download URL for the shared file.
    """
    if not path:
        raise ValueError("path wajib diisi")
    dav_base, instance_base, username, password = _get_credentials()
    rp = path.replace("\\", "/")
    if not rp.startswith("/"):
        rp = "/" + rp
    # Construct the OCS API endpoint
    url = f"{instance_base}/ocs/v2.php/apps/files_sharing/api/v1/shares"
    data = {"path": rp, "shareType": "3", "permissions": "1"}
    headers = {"OCS-APIRequest": "true", "Accept": "application/xml"}
    resp = requests.post(url, data=data, auth=(username, password), headers=headers)
    if not (200 <= resp.status_code < 300):
        raise RuntimeError(
            f"Gagal membuat share link di Nextcloud (status {resp.status_code})"
        )
    from xml.etree import ElementTree as ET
    xml = ET.fromstring(resp.content)
    share_url = None
    # Find the first <url> element
    for elem in xml.iter():
        if elem.tag.lower().endswith("url") and elem.text:
            share_url = elem.text.strip()
            break
    if not share_url:
        raise RuntimeError("Response OCS tidak mengandung URL share")
    # Append /download for direct file download
    return share_url.rstrip("/") + "/download"

def delete_object(path: str) -> None:
    """
    Menghapus file atau folder dari Nextcloud via WebDAV.
    """
    if not path:
        raise ValueError("path wajib diisi")
    
    dav_base, _, username, password = _get_credentials()
    remote_path = path.replace("\\", "/").strip("/")
    url = dav_base + remote_path
    
    # Mengirimkan request DELETE ke Nextcloud
    resp = requests.delete(url, auth=(username, password))
    
    # Status 204 (No Content) atau 200 adalah sukses. 
    # Status 404 dianggap sukses karena target memang sudah tidak ada.
    if resp.status_code not in (204, 200, 404):
        raise RuntimeError(f"Gagal menghapus objek di Nextcloud (status {resp.status_code})")