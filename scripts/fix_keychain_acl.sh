#!/bin/bash
# fix_keychain_acl.sh — Grant python3.12 "Always Allow" access to ALL nougenshards-vault entries
# This eliminates the macOS Keychain popup that blocks autonomous/headless Python vault access.
#
# Usage: ./fix_keychain_acl.sh
# You will be prompted for your login keychain password ONCE.

set -euo pipefail

SERVICE="nougenshards-vault"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

echo "🔐 NouGen Keychain ACL Fixer"
echo "This will grant python3 'Always Allow' access to all $SERVICE entries."
echo ""

# Prompt for keychain password
read -sp "Enter your login keychain password: " KC_PASS
echo ""

# Unlock the keychain first
security unlock-keychain -p "$KC_PASS" "$KEYCHAIN" 2>/dev/null || {
    echo "❌ Failed to unlock keychain. Wrong password?"
    exit 1
}
echo "✅ Keychain unlocked"

# Get all account names for our service
ACCOUNTS=$(security dump-keychain "$KEYCHAIN" 2>/dev/null | awk -v svc="$SERVICE" '
    /0x00000007/ && index($0, svc) { found=1 }
    found && /\"acct\"/ { 
        gsub(/.*=\"/, ""); gsub(/"/, ""); print; found=0 
    }
')

COUNT=$(echo "$ACCOUNTS" | wc -l | tr -d ' ')
echo "📦 Found $COUNT keychain entries to update"
echo ""

SUCCESS=0
FAIL=0

while IFS= read -r acct; do
    [ -z "$acct" ] && continue
    
    # Set the partition list to allow all apple tools + python
    # The partition list controls which apps can access without prompting
    if security set-generic-password-partition-list \
        -S "apple-tool:,apple:,teamid:,apple:" \
        -s "$SERVICE" \
        -a "$acct" \
        -k "$KC_PASS" \
        "$KEYCHAIN" 2>/dev/null; then
        ((SUCCESS++))
    else
        echo "  ⚠️  Failed: $acct"
        ((FAIL++))
    fi
done <<< "$ACCOUNTS"

echo ""
echo "✅ Updated $SUCCESS entries"
[ "$FAIL" -gt 0 ] && echo "⚠️  Failed $FAIL entries" || true
echo ""
echo "🚀 Python can now access the vault without keychain popups."
echo "   Test with: python3 -c 'import keyring; print(keyring.get_password(\"nougenshards-vault\", \"default-api-key\"))'"
