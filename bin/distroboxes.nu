#!/usr/bin/env nu

# Distrobox management script
# Create, list, and remove distroboxes for various Linux distributions

# Check if distrobox is installed
def check-distrobox [] {
  if (which distrobox | is-empty) {
    print $"(ansi red)✗ distrobox is not installed(ansi reset)"
    print $"(ansi green)→ Please install distrobox first:(ansi reset)"
    print "  - On Fedora: sudo dnf install distrobox"
    print "  - On Ubuntu/Debian: sudo apt install distrobox"
    print "  - On Arch: sudo pacman -S distrobox"
    print "  - Or visit: https://distrobox.it/"
    error make {
      msg: "distrobox is not installed"
    }
  }
}

# Check if a distrobox exists
def box-exists [
  name: string  # Name of the distrobox to check
]: nothing -> bool {
  let result = (do -i { ^distrobox list } | complete)
  if $result.exit_code != 0 {
    return false
  }

  let boxes = ($result.stdout | lines | skip 1 | parse "{id}|{name}|{status}|{image}" | get name)
  $name in $boxes
}

# Log a message with green arrow
def log [message: string] {
  print $"(ansi green)→ ($message)(ansi reset)"
}

# Log an error message with red X
def log-error [message: string] {
  print $"(ansi red)✗ ($message)(ansi reset)"
}

# Log a warning message with yellow exclamation
def log-warning [message: string] {
  print $"(ansi yellow)! ($message)(ansi reset)"
}

# Log a dry-run message with cyan color
def log-dry-run [message: string] {
  print $"(ansi cyan)[DRY RUN] ($message)(ansi reset)"
}

# Create a single distrobox
def create-box [
  name: string   # Name of the distrobox
  image: string  # Container image to use
  --dry-run      # Dry run mode - don't actually create
]: nothing -> bool {
  log $"Checking distrobox '($name)'..."

  if (box-exists $name) {
    log $"Distrobox '($name)' already exists, skipping..."
    return true
  }

  if $dry_run {
    log-dry-run $"Would create distrobox '($name)' with image '($image)'"
    return true
  }

  log $"Creating distrobox '($name)' with image '($image)'..."

  let result = (do -i { ^distrobox create --name $name --image $image --yes } | complete)

  if $result.exit_code == 0 {
    log $"Successfully created distrobox '($name)'"
    return true
  } else {
    log-error $"Failed to create distrobox '($name)'"
    return false
  }
}

# Create all predefined distroboxes
def "main create" [
  --dry-run (-n)  # Dry run mode - show what would be done without doing it
] {
  check-distrobox

  if $dry_run {
    log-dry-run "Running in dry-run mode - no changes will be made"
    print ""
  }

  let boxes = [
    {name: "ubuntu", image: "ubuntu:latest"},
    {name: "debian", image: "debian:latest"},
    {name: "fedora", image: "fedora:latest"},
    {name: "arch", image: "archlinux:latest"},
    {name: "tumbleweed", image: "opensuse/tumbleweed:latest"}
  ]

  log "Starting distrobox creation process..."
  print ""

  let failed = $boxes | each { |box|
    let success = (create-box $box.name $box.image --dry-run=$dry_run)
    print ""
    if not $success {
      $box.name
    }
  } | compact

  if ($failed | is-empty) {
    if $dry_run {
      log-dry-run "All distroboxes would be created successfully!"
    } else {
      log "All distroboxes created successfully!"
      print ""
      log "Available distroboxes:"
      ^distrobox list
    }
  } else {
    log-error $"Failed to create the following distroboxes: ($failed | str join ', ')"
    error make {
      msg: "Some distroboxes failed to create"
    }
  }
}

# List all existing distroboxes
def "main list" [] {
  check-distrobox
  log "Existing distroboxes:"
  ^distrobox list
}

# Remove a single distrobox
def remove-box [
  name: string  # Name of the distrobox to remove
  --dry-run     # Dry run mode - don't actually remove
]: nothing -> bool {
  if not (box-exists $name) {
    log-warning $"Distrobox '($name)' does not exist"
    return false
  }

  if $dry_run {
    log-dry-run $"Would remove distrobox '($name)'"
    return true
  }

  log $"Removing distrobox '($name)'..."

  let result = (do -i { ^distrobox rm $name --yes } | complete)

  if $result.exit_code == 0 {
    log $"Successfully removed distrobox '($name)'"
    return true
  } else {
    log-error $"Failed to remove distrobox '($name)'"
    return false
  }
}

# Remove all distroboxes (interactive)
def "main remove" [
  --dry-run (-n)  # Dry run mode - show what would be removed without removing
] {
  check-distrobox

  if $dry_run {
    log-dry-run "Running in dry-run mode - no changes will be made"
    print ""
  }

  log-warning "This will remove all distroboxes!"
  let response = (input "Are you sure? (y/N): ")

  if $response !~ "(?i)^y(es)?$" {
    log "Operation cancelled"
    return
  }

  let boxes = (do -i { ^distrobox list | lines | skip 1 | parse "{id}|{name}|{status}|{image}" | get name } | complete)

  if $boxes.exit_code != 0 or ($boxes.stdout | is-empty) {
    log "No distroboxes found"
    return
  }

  log "Removing all distroboxes..."

  let box_names = ($boxes.stdout | lines | skip 1 | parse "{id}|{name}|{status}|{image}" | get name)
  let failed = $box_names | each { |box|
    if not (remove-box $box --dry-run=$dry_run) {
      $box
    }
  } | compact

  if ($failed | is-empty) {
    if $dry_run {
      log-dry-run "All distroboxes would be removed successfully"
    } else {
      log "All distroboxes removed successfully"
    }
  } else {
    log-error $"Failed to remove: ($failed | str join ', ')"
    error make {
      msg: "Some distroboxes failed to remove"
    }
  }
}

# Show help message
def "main help" [] {
  print "Usage: distroboxes.nu [COMMAND] [OPTIONS]"
  print ""
  print "Commands:"
  print "  create     Create all distroboxes (default)"
  print "  list       List existing distroboxes"
  print "  remove     Remove all distroboxes (interactive)"
  print "  help       Show this help message"
  print ""
  print "Options:"
  print "  -n, --dry-run    Show what would be done without doing it"
  print ""
  print "Distroboxes created:"
  print "  - ubuntu (latest)"
  print "  - debian (latest)"
  print "  - fedora (latest)"
  print "  - arch (latest)"
  print "  - tumbleweed (latest)"
  print ""
  print "Examples:"
  print "  distroboxes.nu create           # Create all distroboxes"
  print "  distroboxes.nu create --dry-run # Preview what would be created"
  print "  distroboxes.nu list             # List existing boxes"
  print "  distroboxes.nu remove           # Remove all boxes"
  print "  distroboxes.nu remove -n        # Preview what would be removed"
}

# Main entry point - defaults to create command
def main [] {
  main create
}

