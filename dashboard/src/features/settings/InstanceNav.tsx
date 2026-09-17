import { Globe, HardDrive, History, Server } from "lucide-react";
import { NavTabs } from "../../components/ui/Tabs";

/** Sub-navigation shared by the instance-owner settings pages. */
export function InstanceNav() {
  const icon = "size-4";
  return (
    <NavTabs
      className="mb-5"
      items={[
        { to: "/settings/instance", label: "Instance", icon: <Server className={icon} /> },
        { to: "/settings/devices", label: "Devices", icon: <HardDrive className={icon} /> },
        { to: "/settings/backups", label: "Backups", icon: <History className={icon} /> },
        { to: "/settings/remote-access", label: "Domains & remote access", icon: <Globe className={icon} /> },
      ]}
    />
  );
}
