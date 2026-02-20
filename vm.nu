#!/usr/bin/env nu

def print-help [] {
  print ""
  print "Usage:  nu vm.nu [target] [--clean]"
  print ""
  print "If no target provided, shows interactive picker."
  print "Target names are automatically appended with '-vm'."
  print ""
  print "Options:"
  print "  -c, --clean    Remove ./<target>-vm.qcow2 before building"
  print "  -h, --help     Show this help"
  print ""
}

def get-vm-targets [] {
  let system = "x86_64-linux"
  let output = do { ^nix eval $".#packages.($system)" --json --apply "pkgs: builtins.attrNames pkgs" } | complete

  if $output.exit_code == 0 {
    $output.stdout | from json | where ($it | str ends-with "-vm")
  } else {
    []
  }
}

def main [
  target?: string
  --clean(-c)
  --help(-h)
] {
  if $help or ($target == "help") {
    print-help
    return
  }

  let full_target = if ($target == null) {
    let vm_targets = get-vm-targets
    if ($vm_targets | length) == 0 {
      print "Error: No VM targets found in flake"
      exit 1
    }
    if ($vm_targets | length) == 1 { $vm_targets.0 } else {
      $vm_targets | input list "Select target:"
    }
  } else if ($target | str ends-with "-vm") {
    $target
  } else {
    $"($target)-vm"
  }

  let qcow = $"./($full_target).qcow2"

  print $"Using target: ($full_target)"

  if $clean and ($qcow | path exists) {
    print $"Removing ($qcow)"
    rm -f $qcow
  }

  print $"Building target ($full_target)..."
  ^nix build $".#($full_target)"

  print $"Running target ($full_target)..."
  ^nix run $".#($full_target)"
}
