#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
#   "cryptography>=42",
# ]
# ///
# ruff: noqa: T201  # this is an operator-facing CLI; print() is the interface
"""WI-INT-7: post-deploy smoke test against a live PerchPub deployment.

Walks the real station lifecycle end-to-end against a deployed stack:

    operator login -> enrollment session -> device keypair + CSR ->
    step-ca-signed leaf -> mTLS media upload -> poll for the Observation

Unlike the in-process compose-smoke test (WI-INT-5), this presents a *real*
device certificate to the prod Traefik mTLS entrypoint via httpx ``cert=``
(a genuine TLS client-auth handshake), not a hand-stuffed
``X-Forwarded-Tls-Client-Cert`` header. It is the post-deploy verification
step referenced by deploy/terraform/README.md and deployment.md.

Two base URLs are involved, because the prod edge splits them
(deploy/traefik/dynamic/dynamic.yml):

  * ``--api-url``   (public :443) — health, login, enrollment create/confirm.
  * ``--mtls-url``  (mTLS  :8443) — upload + classify-task poll. Requires the
                    device cert. Defaults to ``--api-url`` with port 8443.

Run it standalone (uv resolves the inline deps)::

    uv run scripts/deploy-smoke.py \\
        --api-url https://api.perchpub.net \\
        --operator-email admin@perchpub.net   # password via $PERCHPUB_OPERATOR_PASSWORD

Exit 0 = the deployment ingested and classified an upload end-to-end.
A non-zero exit names the stage that failed.

The ``--no-mtls`` mode hits a single plain base URL and hand-stuffs the cert
header instead of doing a real handshake — for rehearsing against the dev
stack (no Traefik; FU-11) before a real deploy exists.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.x509.oid import NameOID

# A tiny (~1.5 KB) valid H.264/MP4 clip — 4 green frames at 64x64 — embedded so
# the smoke is zero-config. The worker decodes it with OpenCV
# (app/tasks.py:classify_video); any real decodable clip reaches Success, so
# this stands in for a station capture. Override with --media-file.
_SAMPLE_MP4_B64 = """
AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAMzbW9vdgAAAGxtdmhkAAAAAAAAAAAA
AAAAAAAD6AAAA+gAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAA
AABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAl50cmFrAAAAXHRraGQAAAADAAAA
AAAAAAAAAAABAAAAAAAAA+gAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAA
AAAAAAAAAABAAAAAAEAAAABAAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAPoAAAAAAABAAAA
AAHWbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAABAAAAAQABVxAAAAAAALWhkbHIAAAAAAAAAAHZp
ZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABgW1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAA
ACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAAUFzdGJsAAAAuXN0c2QAAAAAAAAA
AQAAAKlhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAEAAQABIAAAASAAAAAAAAAABFUxhdmM2
MS4xOS4xMDEgbGlieDI2NAAAAAAAAAAAAAAAGP//AAAAL2F2Y0MBQsAK/+EAF2dCwArZBCbARAAA
AwAEAAADACA8SJkgAQAFaMuDyyAAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAAVuAAAAAAA
AAAYc3R0cwAAAAAAAAABAAAABAAAEAAAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAA
AAEAAAABAAAABAAAAAEAAAAkc3RzegAAAAAAAAAAAAAABAAAApgAAAAKAAAACwAAAAoAAAAUc3Rj
bwAAAAAAAAABAAADYwAAAGF1ZHRhAAAAWW1ldGEAAAAAAAAAIWhkbHIAAAAAAAAAAG1kaXJhcHBs
AAAAAAAAAAAAAAAALGlsc3QAAAAkqXRvbwAAABxkYXRhAAAAAQAAAABMYXZmNjEuNy4xMDIAAAAI
ZnJlZQAAAr9tZGF0AAACcAYF//9s3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NCByMzEw
OCAzMWUxOWY5IC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyMyAt
IGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTAgcmVm
PTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MToweDExMSBtZT1oZXggc3VibWU9NyBwc3k9MSBw
c3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxs
aXM9MSA4eDhkY3Q9MCBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3Fw
X29mZnNldD0tMiB0aHJlYWRzPTIgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0w
IG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVk
X2ludHJhPTAgYmZyYW1lcz0wIHdlaWdodHA9MCBrZXlpbnQ9MjUwIGtleWludF9taW49NCBzY2Vu
ZWN1dD00MCBpbnRyYV9yZWZyZXNoPTAgcmNfbG9va2FoZWFkPTQwIHJjPWNyZiBtYnRyZWU9MSBj
cmY9MjMuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBzdGVwPTQgaXBfcmF0aW89MS40
MCBhcT0xOjEuMDAAgAAAACBliIQEvEYoAAqLxwABJ7jgACZnJycnXXXXXXXXXXXXgAAAAAZBmjgJ
eEYAAAAHQZpUAj4RgAAAAAZBmmAQ8Iw=
"""

_HEALTH = "/api/v1/utils/health-check/"
_LOGIN = "/api/v1/login/access-token"  # noqa: S105 - URL path, not a secret
_ENROLL_CREATE = "/api/v1/enrollment/create"


class SmokeError(Exception):
    """A stage of the smoke flow failed; message names the stage."""


def _log(msg: str) -> None:
    print(msg, flush=True)


def _make_keypair_and_csr(
    common_name: str, key_type: str
) -> tuple[ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey, str]:
    """Generate a device keypair + CSR, mirroring tests/utils/mtls.make_csr.

    Ed25519 is the recommended default; EC P-256 is the supported alternative.
    Ed25519 signs the CSR with no hash algorithm; EC requires SHA-256.
    """
    key: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey
    algorithm: hashes.HashAlgorithm | None
    if key_type == "ed25519":
        key = ed25519.Ed25519PrivateKey.generate()
        algorithm = None
    elif key_type == "ec":
        key = ec.generate_private_key(ec.SECP256R1())
        algorithm = hashes.SHA256()
    else:
        raise SmokeError(f"unsupported --key-type: {key_type!r}")

    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, algorithm)
    )
    return key, csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def _write_credentials(
    out_dir: Path,
    key: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey,
    cert_pem: str,
    ca_chain_pem: str | None,
) -> tuple[Path, Path]:
    """Persist device.key (0600) + device.crt + ca_chain.pem; return (crt, key)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = out_dir / "device.key"
    crt_path = out_dir / "device.crt"

    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(key_pem)
    key_path.chmod(0o600)
    crt_path.write_text(cert_pem)
    if ca_chain_pem:
        (out_dir / "ca_chain.pem").write_text(ca_chain_pem)
    return crt_path, key_path


def _resolve_mtls_url(api_url: str, mtls_url: str | None) -> str:
    if mtls_url:
        return mtls_url.rstrip("/")
    parsed = urllib.parse.urlparse(api_url)
    return parsed._replace(netloc=f"{parsed.hostname}:8443").geturl().rstrip("/")


def run_smoke(args: argparse.Namespace) -> None:
    password = args.operator_password or os.environ.get("PERCHPUB_OPERATOR_PASSWORD")
    if not password:
        raise SmokeError(
            "operator password required: pass --operator-password or set "
            "$PERCHPUB_OPERATOR_PASSWORD"
        )

    verify: bool | str = False if args.insecure else (args.cacert or True)
    api_url = args.api_url.rstrip("/")
    station_cn = args.station_cn or f"smoke-{uuid.uuid4().hex[:8]}"

    if args.media_file:
        media = Path(args.media_file).read_bytes()
        media_name = Path(args.media_file).name
    else:
        media = base64.b64decode("".join(_SAMPLE_MP4_B64.split()))
        media_name = "smoke.mp4"

    # --- Stage 1-4: health, login, enroll (always over the public :443 edge) ---
    with httpx.Client(base_url=api_url, verify=verify, timeout=args.timeout) as pub:
        _log(f"[1/6] health-check {api_url}{_HEALTH}")
        health = pub.get(_HEALTH)
        if health.status_code != 200:
            raise SmokeError(f"health-check failed: HTTP {health.status_code}")

        _log(f"[2/6] operator login as {args.operator_email}")
        login = pub.post(
            _LOGIN, data={"username": args.operator_email, "password": password}
        )
        if login.status_code != 200:
            raise SmokeError(f"login failed: HTTP {login.status_code} {login.text}")
        bearer = login.json()["access_token"]
        auth = {"Authorization": f"Bearer {bearer}"}

        _log(f"[3/6] open enrollment session (lat={args.lat}, lon={args.lon})")
        create = pub.post(
            _ENROLL_CREATE,
            json={"latitude": args.lat, "longitude": args.lon},
            headers=auth,
        )
        if create.status_code != 200:
            raise SmokeError(
                f"enrollment/create failed: HTTP {create.status_code} {create.text}"
            )
        sess = create.json()

        _log(f"[4/6] confirm enrollment ({args.key_type} key, CN={station_cn})")
        key, csr_pem = _make_keypair_and_csr(station_cn, args.key_type)
        confirm = pub.post(
            f"/api/v1/enrollment/confirm/{sess['session_id']}",
            json={"auth_token": sess["auth_token"], "csr_pem": csr_pem},
        )
        if confirm.status_code != 200:
            raise SmokeError(
                f"enrollment/confirm failed: HTTP {confirm.status_code} {confirm.text}"
            )
        enrollment = confirm.json()
        if not enrollment.get("success") or not enrollment.get("certificate_pem"):
            raise SmokeError(f"enrollment did not issue a certificate: {enrollment}")

        leaf = x509.load_pem_x509_certificate(
            enrollment["certificate_pem"].encode("utf-8")
        )
        expected = (
            Ed25519PublicKey if args.key_type == "ed25519" else EllipticCurvePublicKey
        )
        if not isinstance(leaf.public_key(), expected):
            raise SmokeError(
                f"issued leaf key type does not match requested {args.key_type!r}"
            )
        station_id = enrollment["station_id"]
        crt_path, key_path = _write_credentials(
            Path(args.out_dir),
            key,
            enrollment["certificate_pem"],
            enrollment.get("ca_chain_pem"),
        )
        _log(f"      enrolled station {station_id}; cert -> {crt_path}")

        # --- Stage 5-6: upload + poll. Real mTLS, or hand-stuffed header. ---
        if args.no_mtls:
            _log("[5/6] upload via hand-stuffed cert header (--no-mtls)")
            header = {
                args.mtls_header: urllib.parse.quote(enrollment["certificate_pem"])
            }
            upload = pub.post(
                "/api/v1/upload/",
                files={"file": (media_name, media, "video/mp4")},
                headers=header,
            )
            task_id = _upload_task_id(upload)
            status, latest = _poll(pub, task_id, args.poll_timeout, headers=header)
        else:
            mtls_url = _resolve_mtls_url(api_url, args.mtls_url)
            _log(f"[5/6] upload via real mTLS handshake to {mtls_url}/api/v1/upload/")
            with httpx.Client(
                base_url=mtls_url,
                verify=verify,
                cert=(str(crt_path), str(key_path)),
                timeout=args.timeout,
            ) as mtls:
                upload = mtls.post(
                    "/api/v1/upload/",
                    files={"file": (media_name, media, "video/mp4")},
                )
                task_id = _upload_task_id(upload)
                status, latest = _poll(mtls, task_id, args.poll_timeout)

    _log(f"[6/6] classify task {task_id} terminal status: {status}")
    if status != "Success":
        if status is None:
            raise SmokeError(
                f"classify task {task_id} never reached a terminal state within "
                f"{args.poll_timeout}s — worker not draining Redis, or the prod "
                f"classifier model is missing from S3 (see FOLLOWUPS FU-26). Last: {latest}"
            )
        raise SmokeError(
            f"classify task ended {status!r}, not Success. "
            f"file_metadata={latest.get('file_metadata')}"
        )

    observation = latest.get("observation")
    if not observation:
        raise SmokeError(f"task succeeded but carries no observation: {latest}")
    obs_station = (observation.get("station") or {}).get("id")
    if obs_station != station_id:
        raise SmokeError(
            f"observation station {obs_station} != enrolled station {station_id}"
        )
    _log(
        "      observation "
        f"{observation.get('id')} species_id={observation.get('species_id')} "
        f"confidence={observation.get('confidence_score')}"
    )
    _log("\nSMOKE PASS: deployment ingested and classified an upload end-to-end.")


def _upload_task_id(resp: httpx.Response) -> str:
    if resp.status_code != 200:
        raise SmokeError(f"upload failed: HTTP {resp.status_code} {resp.text}")
    task_id = resp.json().get("id")
    if not task_id:
        raise SmokeError(f"upload returned no task id: {resp.text}")
    return str(task_id)


def _poll(
    client: httpx.Client,
    task_id: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Poll classify-task until Success/Failed or timeout. Returns (status, body)."""
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        poll = client.get(f"/api/v1/classify-task/{task_id}", headers=headers)
        if poll.status_code != 200:
            raise SmokeError(f"poll failed: HTTP {poll.status_code} {poll.text}")
        latest = poll.json()
        if latest.get("status") in ("Success", "Failed"):
            return str(latest["status"]), latest
        time.sleep(1.0)
    return None, latest


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Post-deploy smoke test for a live PerchPub deployment.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--api-url",
        required=True,
        help="public API base, e.g. https://api.perchpub.net",
    )
    p.add_argument(
        "--mtls-url", default=None, help="mTLS base (default: --api-url with :8443)"
    )
    p.add_argument("--operator-email", required=True, help="superuser email for login")
    p.add_argument(
        "--operator-password",
        default=None,
        help="superuser password (default: $PERCHPUB_OPERATOR_PASSWORD)",
    )
    p.add_argument(
        "--station-cn", default=None, help="device CN (default: smoke-<random>)"
    )
    p.add_argument("--key-type", choices=["ed25519", "ec"], default="ed25519")
    p.add_argument(
        "--lat", type=float, default=0.0, help="station latitude for enrollment"
    )
    p.add_argument(
        "--lon", type=float, default=0.0, help="station longitude for enrollment"
    )
    p.add_argument(
        "--media-file", default=None, help="clip to upload (default: embedded sample)"
    )
    p.add_argument(
        "--out-dir", default="./smoke-out", help="where to write device.crt/.key"
    )
    p.add_argument(
        "--cacert", default=None, help="custom CA bundle for server TLS verification"
    )
    p.add_argument(
        "--insecure", action="store_true", help="disable server TLS verification"
    )
    p.add_argument(
        "--no-mtls",
        action="store_true",
        help="hand-stuff the cert header against --api-url instead of a real mTLS handshake",
    )
    p.add_argument(
        "--mtls-header",
        default="X-Forwarded-Tls-Client-Cert",
        help="header name for --no-mtls mode (matches settings.MTLS_CLIENT_CERT_HEADER)",
    )
    p.add_argument(
        "--timeout", type=float, default=30.0, help="per-request timeout (s)"
    )
    p.add_argument(
        "--poll-timeout", type=float, default=30.0, help="observation poll budget (s)"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        run_smoke(args)
    except SmokeError as exc:
        print(f"\nSMOKE FAIL: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(
            f"\nSMOKE FAIL: transport error reaching the deployment: {exc}",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"\nSMOKE FAIL: local I/O error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
