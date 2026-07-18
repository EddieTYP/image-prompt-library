#!/usr/bin/env python3
"""Verify a release manifest, checksum sidecar, and application archive.

This module intentionally uses only the Python standard library so it can run
before an installed runtime exists (and from the release workflow).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath


NAME = "image-prompt-library"
SEMVER_RE = re.compile(
    r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEX40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
PRIVATE_COMPONENTS = {
    ".agents",
    ".codebase-memory",
    ".git",
    ".env",
    ".local-work",
    ".superpowers",
    ".venv",
    "backups",
    "library",
    "logs",
    "node_modules",
    "reports",
    "__pycache__",
}
REQUIRED_FILES = {
    "VERSION",
    "pyproject.toml",
    "backend/main.py",
    "frontend/dist/index.html",
    "scripts/appctl.sh",
    "scripts/install.sh",
    "scripts/load-env.sh",
    "scripts/install-sample-data.sh",
    "scripts/setup-runtime.sh",
    "scripts/verify-release-assets.py",
    "scripts/appctl.ps1",
    "scripts/install.ps1",
    "scripts/install-sample-data.ps1",
    "scripts/setup-runtime.ps1",
}


class VerificationError(ValueError):
    """Raised for a release that cannot be safely installed or published."""


def normalize_version(value: str) -> str:
    """Return the canonical tag form (a strict SemVer tag beginning with v)."""

    if not isinstance(value, str) or not value:
        raise VerificationError("release version is required")
    if value != value.strip():
        raise VerificationError(f"release version is not strict SemVer: {value}")
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise VerificationError(f"release version is not strict SemVer: {value}")
    prerelease = match.group(4)
    if prerelease:
        for identifier in prerelease.split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                raise VerificationError(f"release version is not strict SemVer: {value}")
    return "v" + value.lstrip("v")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path, version: str, artifact_name: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"could not read release manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise VerificationError("release manifest must be a JSON object")
    for key in ("name", "version", "artifact", "sha256", "capabilities"):
        if key not in payload:
            raise VerificationError(f"release manifest is missing {key}")
    if payload["name"] != NAME or payload["version"] != version or payload["artifact"] != artifact_name:
        raise VerificationError("release manifest identity does not match the selected release")
    sha256 = payload["sha256"]
    schema_version = payload.get("schema_version", 1)
    source_sha = payload.get("source_sha")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version not in {1, 2}:
        raise VerificationError("release manifest schema_version is unsupported")
    if not isinstance(sha256, str) or not HEX64_RE.fullmatch(sha256):
        raise VerificationError("release manifest SHA256 is invalid")
    if schema_version >= 2 and source_sha is None:
        raise VerificationError("release manifest is missing source_sha")
    if source_sha is not None and (not isinstance(source_sha, str) or not HEX40_RE.fullmatch(source_sha)):
        raise VerificationError("release manifest source_sha is invalid")
    if not isinstance(payload["capabilities"], list) or not all(
        isinstance(item, str) for item in payload["capabilities"]
    ):
        raise VerificationError("release manifest capabilities are invalid")
    return payload


def _verify_checksum(path: Path, artifact_name: str, expected: str) -> None:
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise VerificationError(f"could not read checksum sidecar: {exc}") from exc
    if len(lines) != 1:
        raise VerificationError("checksum sidecar must contain exactly one entry")
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^\s]+)", lines[0])
    if not match or match.group(2) != artifact_name:
        raise VerificationError("checksum sidecar identity is invalid")
    if match.group(1).lower() != expected.lower():
        raise VerificationError("checksum sidecar does not match the manifest")


def _member_name(member: tarfile.TarInfo) -> tuple[str, tuple[str, ...]]:
    raw = member.name.replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("//") or re.match(r"^[A-Za-z]:", raw):
        raise VerificationError(f"unsafe archive member: {member.name}")
    if raw.endswith("/"):
        raw = raw.rstrip("/")
    parts = raw.split("/")
    if any(not part or part in {".", ".."} or ":" in part or part.endswith((".", " ")) for part in parts):
        raise VerificationError(f"unsafe archive member: {member.name}")
    canonical = tuple(part.casefold() for part in parts)
    private_pattern = any(
        part in PRIVATE_COMPONENTS
        or part.startswith(".env.")
        or part.startswith(".codex")
        or part.startswith(".qa-")
        for part in canonical
    )
    private_docs = len(canonical) >= 2 and canonical[0] == "docs" and canonical[1] in {"plans", "qa"}
    if private_pattern or private_docs or raw.casefold().endswith(".pyc"):
        raise VerificationError(f"forbidden private/runtime archive member: {member.name}")
    if member.issym() or member.islnk() or member.isdev():
        raise VerificationError(f"unsupported archive member: {member.name}")
    if not member.isfile() and not member.isdir():
        raise VerificationError(f"unsupported archive member: {member.name}")
    return raw, canonical


def _verify_archive(path: Path, expected_version: str, extract_to: Path | None) -> None:
    try:
        archive = tarfile.open(path, mode="r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise VerificationError(f"could not open release archive: {exc}") from exc
    names: dict[tuple[str, ...], tuple[str, str]] = {}
    files: set[str] = set()
    file_paths: set[tuple[str, ...]] = set()
    members: list[tuple[tarfile.TarInfo, str, tuple[str, ...]]] = []
    with archive:
        for member in archive.getmembers():
            raw, canonical = _member_name(member)
            if canonical in names:
                raise VerificationError(f"duplicate or case-conflicting archive member: {member.name}")
            if any(parent in file_paths for index in range(1, len(canonical)) for parent in (canonical[:index],)):
                raise VerificationError(f"archive file/directory conflict: {member.name}")
            if member.isfile() and any(existing[: len(canonical)] == canonical for existing in names):
                raise VerificationError(f"archive file/directory conflict: {member.name}")
            kind = "file" if member.isfile() else "directory"
            names[canonical] = (raw, kind)
            if member.isfile():
                files.add(raw)
                file_paths.add(canonical)
            members.append((member, raw, canonical))
        if not REQUIRED_FILES.issubset(files):
            missing = ", ".join(sorted(REQUIRED_FILES - files))
            raise VerificationError(f"release archive is incomplete; missing {missing}")
        version_members = [member for member, raw, _ in members if raw == "VERSION" and member.isfile()]
        if len(version_members) != 1:
            raise VerificationError("release archive must contain exactly one VERSION file")
        extracted = archive.extractfile(version_members[0])
        version_payload = extracted.read().decode("utf-8") if extracted is not None else ""
        if version_payload.strip() != expected_version or not version_payload.strip():
            raise VerificationError("release archive VERSION does not match the selected release")
        if extract_to is None:
            return
        if extract_to.exists():
            raise VerificationError(f"extraction destination already exists: {extract_to}")
        extract_to.mkdir(parents=True)
        try:
            for member, raw, _ in members:
                destination = extract_to.joinpath(*PurePosixPath(raw).parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise VerificationError(f"archive member has no data: {raw}")
                with destination.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
                mode = member.mode & 0o777
                if mode:
                    destination.chmod(mode)
        except Exception:
            # The caller owns this exact fresh staging path and may remove it.
            raise


def verify_release(
    *,
    version: str,
    manifest_path: Path,
    artifact_path: Path,
    checksum_path: Path,
    expected_source_sha: str | None = None,
    required_capability: str | None = None,
    extract_to: Path | None = None,
) -> dict[str, object]:
    canonical_version = normalize_version(version)
    artifact_name = f"{NAME}-{canonical_version}.tar.gz"
    if artifact_path.name != artifact_name:
        raise VerificationError("artifact filename does not match the selected release")
    if manifest_path.name != f"{NAME}-{canonical_version}.manifest.json":
        raise VerificationError("manifest filename does not match the selected release")
    if checksum_path.name != artifact_name + ".sha256":
        raise VerificationError("checksum filename does not match the selected release")
    manifest = _load_manifest(manifest_path, canonical_version, artifact_name)
    if expected_source_sha is not None:
        source_sha = manifest.get("source_sha")
        if (
            not HEX40_RE.fullmatch(expected_source_sha)
            or not isinstance(source_sha, str)
            or source_sha.lower() != expected_source_sha.lower()
        ):
            raise VerificationError("release manifest source_sha does not match the checked-out source")
    if required_capability and required_capability not in manifest["capabilities"]:
        raise VerificationError(f"release manifest lacks required capability {required_capability}")
    expected = str(manifest["sha256"])
    _verify_checksum(checksum_path, artifact_name, expected)
    actual = _sha256(artifact_path)
    if actual.lower() != expected.lower():
        raise VerificationError("artifact SHA256 does not match the release manifest")
    _verify_archive(artifact_path, canonical_version, extract_to)
    return manifest


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", nargs="?", type=Path)
    parser.add_argument("version", nargs="?")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument("--release-dir", dest="release_dir_option", type=Path)
    parser.add_argument("--version", dest="version_option")
    parser.add_argument("--source-sha")
    parser.add_argument("--capability")
    parser.add_argument("--extract-to", type=Path)
    args = parser.parse_args(argv)
    if args.release_dir_option is not None:
        args.release_dir = args.release_dir_option
    if args.version_option is not None:
        args.version = args.version_option
    if not args.version:
        parser.error("a release version is required")
    if args.release_dir and not any((args.manifest, args.artifact, args.checksum)):
        canonical = normalize_version(args.version)
        artifact = f"{NAME}-{canonical}.tar.gz"
        args.artifact = args.release_dir / artifact
        args.manifest = args.release_dir / f"{NAME}-{canonical}.manifest.json"
        args.checksum = args.release_dir / (artifact + ".sha256")
    if not all((args.manifest, args.artifact, args.checksum)):
        parser.error("provide --manifest, --artifact, and --checksum (or a release directory)")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv or sys.argv[1:])
        verify_release(
            version=args.version,
            manifest_path=args.manifest,
            artifact_path=args.artifact,
            checksum_path=args.checksum,
            expected_source_sha=args.source_sha,
            required_capability=args.capability,
            extract_to=args.extract_to,
        )
    except (VerificationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Verified release assets for {normalize_version(args.version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
