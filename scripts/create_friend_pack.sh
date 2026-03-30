#!/bin/bash
# [Nexus Singularity v30.7] Friend Pack Generator
# Usage: ./create_friend_pack.sh

TARGET="nexus_friend_pack.zip"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "// Nexus: Generating Friend Pack..."

cd "$SCRIPT_DIR"
zip -j "$TARGET" nexus.sh nexus_pilot_cli.py nexus_chat_cli.py

if [ $? -eq 0 ]; then
    echo "// SUCCESS: Created $SCRIPT_DIR/$TARGET"
    echo "// You can now send this file to your friend."
else
    echo "// ERROR: Failed to create zip pack."
fi
