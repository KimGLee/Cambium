"""Bounded exact-URL transfer shared by locked Host providers.

Callers retain the mandatory pinned digest check before extraction/execution.
"""

import http.client
import io
import re
import urllib.request
import urllib.parse

from Tools.platform.common.host_environment import HostEnvironmentUnavailable


def download(request, *, capability_id, limit, redirect_hosts=()):
    """Bounded transfer of one immutable URL; partial bytes never execute.

    Some networks terminate a response before Content-Length. Resume only an
    exact Content-Range from this same URL, at most twice, then verify the
    complete archive against the original lock (not a server-supplied hash).
    """
    output, expected = io.BytesIO(), None
    detail = "Pinned download did not complete"
    for _attempt in range(3):
        offset = output.tell()
        headers = {"Accept-Encoding": "identity", "User-Agent": "Cambium-Host-Preparation", "Cache-Control": "no-cache"}
        if offset:
            headers["Range"] = "bytes=%d-" % offset
        try:
            with urllib.request.urlopen(urllib.request.Request(request["url"], headers=headers), timeout=60) as response:
                if response.geturl() != request["url"] and not (
                        urllib.parse.urlparse(response.geturl()).scheme == "https" and
                        urllib.parse.urlparse(response.geturl()).hostname in redirect_hosts):
                    raise ValueError("Pinned download redirected outside its pinned URL")
                response_headers = getattr(response, "headers", {})
                status = response.getcode() if hasattr(response, "getcode") else 200
                if status == 206:
                    span = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response_headers.get("Content-Range", ""))
                    if span is None or int(span[1]) != offset or int(span[2]) + 1 != int(span[3]) or \
                            (expected is not None and int(span[3]) != expected):
                        raise ValueError("Pinned download returned an inconsistent Content-Range")
                    expected = int(span[3])
                elif status == 200:
                    output = io.BytesIO()
                    size = response_headers.get("Content-Length")
                    expected = int(size) if size and size.isdigit() else None
                else:
                    raise ValueError("Unexpected Pinned download response")
                if expected is not None and expected > limit:
                    raise ValueError("Pinned archive exceeds download limit")
                while output.tell() <= limit:
                    chunk = response.read(min(1024 * 1024, limit + 1 - output.tell()))
                    if not chunk:
                        break
                    output.write(chunk)
                if output.tell() > limit:
                    raise ValueError("Pinned archive exceeds download limit")
                if expected is None or output.tell() == expected:
                    return output.getvalue()
                detail = "Pinned download incomplete: expected %d bytes, received %d" % (expected, output.tell())
        except (OSError, http.client.HTTPException) as exc:
            detail = str(exc)
    raise HostEnvironmentUnavailable(detail, capability_id=capability_id,
        code="download-incomplete", resource=request["url"])


__all__ = ["download"]
