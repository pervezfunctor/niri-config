#!/usr/bin/env nu

# Demo script to showcase distroboxes.nu features

print "╔════════════════════════════════════════════════════════════╗"
print "║         Distroboxes.nu - Nushell Script Demo              ║"
print "╚════════════════════════════════════════════════════════════╝"
print ""

print $"(ansi cyan)This demo showcases the converted Nushell script(ansi reset)"
print ""

# Demo 1: Show help
print $"(ansi yellow)═══ Demo 1: Help Command ═══(ansi reset)"
nu bin/distroboxes.nu help
print ""

# Demo 2: Show script features
print $"(ansi yellow)═══ Demo 2: Key Features ═══(ansi reset)"
print "✨ Dry-run mode for safe testing"
print "✨ Type-safe function definitions"
print "✨ Color-coded output"
print "✨ Proper error handling"
print "✨ Subcommand pattern"
print "✨ Follows strict Nushell best practices"
print ""

# Demo 3: Show the script structure
print $"(ansi yellow)═══ Demo 3: Script Structure ═══(ansi reset)"
print "Commands available:"
print "  • create [--dry-run]  - Create all distroboxes"
print "  • list                - List existing distroboxes"
print "  • remove [--dry-run]  - Remove all distroboxes"
print "  • help                - Show help message"
print ""

# Demo 4: Show example usage
print $"(ansi yellow)═══ Demo 4: Example Usage ═══(ansi reset)"
print ""
print $"(ansi green)# Preview what would be created (safe):(ansi reset)"
print "  nu bin/distroboxes.nu create --dry-run"
print ""
print $"(ansi green)# Actually create the boxes:(ansi reset)"
print "  nu bin/distroboxes.nu create"
print ""
print $"(ansi green)# List existing boxes:(ansi reset)"
print "  nu bin/distroboxes.nu list"
print ""
print $"(ansi green)# Preview what would be removed:(ansi reset)"
print "  nu bin/distroboxes.nu remove -n"
print ""

print "╔════════════════════════════════════════════════════════════╗"
print "║                    Demo Complete!                         ║"
print "╚════════════════════════════════════════════════════════════╝"

