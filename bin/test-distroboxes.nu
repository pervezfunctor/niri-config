#!/usr/bin/env nu

# Test script for distroboxes.nu

print "Testing distroboxes.nu script..."
print ""

# Test 1: Help command
print "=== Test 1: Help Command ==="
nu bin/distroboxes.nu help
print ""

# Test 2: Dry-run create
print "=== Test 2: Dry-run Create ==="
nu bin/distroboxes.nu create --dry-run
print ""

# Test 3: List (should work even without distrobox)
print "=== Test 3: List Command ==="
try {
  nu bin/distroboxes.nu list
} catch {
  print "List command failed (expected if distrobox not installed)"
}
print ""

print "Tests completed!"

