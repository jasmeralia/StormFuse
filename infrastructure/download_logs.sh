#!/usr/bin/env bash
# Download, decompress, and delete StormFuse log files from S3 for a given upload UUID.
#
# Usage: download_logs.sh <upload-id> [aws-profile]
#
# The bucket name is fetched from the CloudFormation stack output.
# Files are downloaded to ./<upload-id>/, decompressed in place, then deleted from S3.

set -euo pipefail

STACK_NAME="stormfuse-log-upload"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <upload-id> [aws-profile]" >&2
    exit 1
fi

UPLOAD_ID="$1"
PROFILE_ARGS=()
if [[ $# -ge 2 ]]; then
    PROFILE_ARGS=(--profile "$2")
fi

# Resolve bucket name from CloudFormation stack output.
BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    "${PROFILE_ARGS[@]}" \
    --query "Stacks[0].Outputs[?OutputKey=='LogsBucketName'].OutputValue" \
    --output text)

if [[ -z "$BUCKET" ]]; then
    echo "Error: could not determine bucket name from stack '$STACK_NAME'" >&2
    exit 1
fi

PREFIX="${UPLOAD_ID}/"
OUT_DIR="./${UPLOAD_ID}"

echo "Bucket:    $BUCKET"
echo "Prefix:    $PREFIX"
echo "Local dir: $OUT_DIR"
echo ""

# List objects under this upload prefix.
KEYS=$(aws s3api list-objects-v2 \
    --bucket "$BUCKET" \
    --prefix "$PREFIX" \
    "${PROFILE_ARGS[@]}" \
    --query "Contents[].Key" \
    --output text)

if [[ -z "$KEYS" || "$KEYS" == "None" ]]; then
    echo "No files found for upload ID '$UPLOAD_ID'." >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

DOWNLOADED=()
for KEY in $KEYS; do
    FILENAME=$(basename "$KEY")
    LOCAL_PATH="${OUT_DIR}/${FILENAME}"
    echo "Downloading s3://${BUCKET}/${KEY} → ${LOCAL_PATH}"
    aws s3 cp "s3://${BUCKET}/${KEY}" "$LOCAL_PATH" "${PROFILE_ARGS[@]}"
    DOWNLOADED+=("$KEY")
done

echo ""
echo "Decompressing..."
for FILE in "${OUT_DIR}"/*.gz; do
    [[ -f "$FILE" ]] || continue
    echo "  gunzip $FILE"
    gunzip "$FILE"
done

echo ""
echo "Deleting from S3..."
for KEY in "${DOWNLOADED[@]}"; do
    echo "  delete s3://${BUCKET}/${KEY}"
    aws s3 rm "s3://${BUCKET}/${KEY}" "${PROFILE_ARGS[@]}"
done

echo ""
echo "Done. Logs are in: ${OUT_DIR}/"
