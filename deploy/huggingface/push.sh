#!/usr/bin/env bash
# Publish the committed code to a Hugging Face Space.
#
#   deploy/huggingface/push.sh <hf-username>/<space-name>
#
# A Space builds from a Dockerfile at its repository root, so this assembles one:
# backend/ and frontend/ as committed at HEAD - never .env, uploads or anything
# uncommitted - plus this directory's Dockerfile, start.sh and README. git asks
# for your Hugging Face username and an access token with write permission.
set -euo pipefail

space="${1:?usage: deploy/huggingface/push.sh <hf-username>/<space-name>}"
root="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Everything from HEAD, including the deploy files: a working-tree copy on
# Windows can carry CRLF line endings, which break start.sh in the container.
git -C "$root" archive HEAD backend frontend deploy/huggingface | tar -x -C "$work"
mv "$work"/deploy/huggingface/{Dockerfile,start.sh,README.md} "$work"/
rm -rf "$work/deploy"

cd "$work"
git init -q -b main
git add -A
git commit -qm "Deploy $(git -C "$root" rev-parse --short HEAD)"
git push --force "https://huggingface.co/spaces/$space" main
