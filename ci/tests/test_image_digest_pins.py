"""HOST-14: every Dockerfile FROM and compose image is digest-pinned."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

FROM_RE = re.compile(r"^FROM\s+(\S+)", re.MULTILINE)
COPY_FROM_RE = re.compile(r"^COPY --from=(\S+)", re.MULTILINE)


def test_dockerfile_bases_digest_pinned() -> None:
    text = Path("Dockerfile").read_text(encoding="utf-8")
    refs = FROM_RE.findall(text) + COPY_FROM_RE.findall(text)
    assert refs, "expected base image references"
    for ref in refs:
        if ref == "builder":
            continue  # multi-stage alias, not a registry image
        _name, sep, rest = ref.partition("@")
        assert sep == "@" and rest.startswith("sha256:"), ref


def test_compose_images_digest_pinned_or_locally_built() -> None:
    data = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    for name, svc in data["services"].items():
        image = str(svc.get("image", ""))
        assert image, name
        if "build" in svc:
            # Local build: pinned transitively by the digest-pinned Dockerfile.
            continue
        assert "@sha256:" in image, (name, image)
