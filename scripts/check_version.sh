#!/usr/bin/env bash
# Check that a release tag matches the version in pyproject.toml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TAG="${1:-}"

if [ -z "$TAG" ]; then
    echo "Usage: $0 <release-tag>" >&2
    exit 2
fi

case "$TAG" in
    v*)
        TAG_VERSION="${TAG#v}"
        ;;
    *)
        echo "ERROR: release tag must start with v: $TAG" >&2
        exit 2
        ;;
esac

PYPROJECT_VERSION="$(sed -nE 's/^version = "([^"]+)"/\1/p' "$PROJECT_DIR/pyproject.toml" | head -n 1)"
if [ -z "$PYPROJECT_VERSION" ]; then
    echo "ERROR: Could not read version from pyproject.toml" >&2
    exit 1
fi

if [ "$PYPROJECT_VERSION" != "$TAG_VERSION" ]; then
    echo "ERROR: tag $TAG does not match pyproject version $PYPROJECT_VERSION" >&2
    exit 1
fi

printf 'Version check passed: %s matches pyproject version %s\n' "$TAG" "$PYPROJECT_VERSION"
