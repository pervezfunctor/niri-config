{ vars, ... }:
{
  virtualisation.vmVariant = {
    users.users."${vars.username}" = {
      # password is program
      initialHashedPassword = "$6$BfoVmtuH61kD7GQc$ok1tiEe1SMlJNuROS7h9sPyzvoHwxTV7XANGZxHk7YJUkznBVBUH7kWmjRvVfEQDQDS/GVQ990sg6a9g68iXM/";
    };

    virtualisation.memorySize = 32768;
    virtualisation.cores = 8;
    virtualisation.diskSize = 65536;

    services.openssh.settings.PasswordAuthentication = true;
    virtualisation.graphics = true;
    virtualisation.qemu.options = [
      "-device virtio-vga-gl"
      "-display gtk,gl=on"
    ];
  };
}
