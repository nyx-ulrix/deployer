// Windows integration done by the exe itself: copying itself into the install folder, shortcuts,
// the Apps & Features entry, resume-after-restart and cleanup on uninstall.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using Microsoft.Win32;

namespace DeployerSetup
{
    static class Integration
    {
        const string RunOnceKey = @"Software\Microsoft\Windows\CurrentVersion\RunOnce";
        const string RunOnceValue = "DeployerInstall";

        public static string ControlExe(string installDir)
        {
            return Path.Combine(installDir, AppInfo.ControlExeName);
        }

        /// <summary>Copies the running exe to InstallDir\DeployerControl.exe (stopping an older tray copy first).</summary>
        public static void CopySelf(string installDir)
        {
            Directory.CreateDirectory(installDir);
            string target = ControlExe(installDir);
            if (string.Equals(Path.GetFullPath(target), Path.GetFullPath(AppInfo.ExePath), StringComparison.OrdinalIgnoreCase)) return;
            StopOtherControlInstances();
            Exception last = null;
            for (int i = 0; i < 5; i++)
            {
                try
                {
                    File.Copy(AppInfo.ExePath, target, true);
                    return;
                }
                catch (IOException ex)
                {
                    last = ex;
                    System.Threading.Thread.Sleep(700);
                }
            }
            if (last != null) throw last;
        }

        public static void StopOtherControlInstances()
        {
            int self = Process.GetCurrentProcess().Id;
            foreach (Process p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(AppInfo.ControlExeName)))
            {
                try
                {
                    if (p.Id != self)
                    {
                        p.Kill();
                        p.WaitForExit(5000);
                    }
                }
                catch (Exception)
                {
                }
                finally
                {
                    p.Dispose();
                }
            }
        }

        public static void RegisterResume(string installDir)
        {
            string rundll = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "rundll32.exe");
            // ShellExecute (unlike a plain Run entry) shows the UAC prompt the elevated exe needs.
            string command = "\"" + rundll + "\" shell32.dll,ShellExec_RunDLL \"" + ControlExe(installDir) + "\" /resume";
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(RunOnceKey))
            {
                key.SetValue(RunOnceValue, command, RegistryValueKind.String);
            }
        }

        public static void ClearResume()
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RunOnceKey, true))
                {
                    if (key != null) key.DeleteValue(RunOnceValue, false);
                }
            }
            catch (Exception)
            {
            }
        }

        static string StartMenuDir
        {
            get { return Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms); }
        }

        public static void CreateShortcuts(string installDir, int port, bool desktop)
        {
            string explorer = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe");
            string exe = ControlExe(installDir);
            string url = "http://localhost:" + port + "/";
            CreateLink(Path.Combine(StartMenuDir, "Deployer.lnk"), explorer, url, installDir, exe, "Open the Deployer dashboard in your browser");
            CreateLink(Path.Combine(StartMenuDir, "Deployer Control.lnk"), exe, "/control", installDir, exe, "Start, stop, update and back up Deployer");
            string desktopLink = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Deployer.lnk");
            if (desktop)
                CreateLink(desktopLink, explorer, url, installDir, exe, "Open the Deployer dashboard in your browser");
        }

        /// <summary>Updates the dashboard shortcuts after a port change (only the ones that exist).</summary>
        public static void UpdateDashboardShortcuts(string installDir, int port)
        {
            string explorer = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe");
            string exe = ControlExe(installDir);
            string url = "http://localhost:" + port + "/";
            string[] links =
            {
                Path.Combine(StartMenuDir, "Deployer.lnk"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Deployer.lnk")
            };
            foreach (string link in links)
            {
                if (File.Exists(link)) CreateLink(link, explorer, url, installDir, exe, "Open the Deployer dashboard in your browser");
            }
        }

        public static void RemoveShortcuts()
        {
            string[] links =
            {
                Path.Combine(StartMenuDir, "Deployer.lnk"),
                Path.Combine(StartMenuDir, "Deployer Control.lnk"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Deployer.lnk")
            };
            foreach (string link in links)
            {
                try
                {
                    if (File.Exists(link)) File.Delete(link);
                }
                catch (Exception)
                {
                }
            }
        }

        public static void RegisterUninstallEntry(string installDir)
        {
            string exe = ControlExe(installDir);
            using (RegistryKey hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
            using (RegistryKey key = hklm.CreateSubKey(AppInfo.UninstallKeyPath))
            {
                key.SetValue("DisplayName", "Deployer");
                key.SetValue("DisplayVersion", AppInfo.Version);
                key.SetValue("Publisher", "Deployer contributors");
                key.SetValue("DisplayIcon", exe + ",0");
                key.SetValue("InstallLocation", installDir);
                key.SetValue("UninstallString", "\"" + exe + "\" /uninstall");
                key.SetValue("QuietUninstallString", "\"" + exe + "\" /uninstall");
                key.SetValue("URLInfoAbout", AppInfo.RepoUrl);
                key.SetValue("HelpLink", AppInfo.TroubleshootingUrl);
                key.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                key.SetValue("EstimatedSize", EstimatedSizeKb(installDir), RegistryValueKind.DWord);
            }
        }

        public static void RemoveUninstallEntry()
        {
            try
            {
                using (RegistryKey hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                {
                    hklm.DeleteSubKeyTree(AppInfo.UninstallKeyPath, false);
                }
            }
            catch (Exception)
            {
            }
        }

        static int EstimatedSizeKb(string dir)
        {
            long bytes = 0;
            try
            {
                foreach (string f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                {
                    try { bytes += new FileInfo(f).Length; } catch (Exception) { }
                }
            }
            catch (Exception)
            {
            }
            // Container images live outside the folder for Docker Desktop / existing Docker; count ~1.5 GB for them.
            bytes = Math.Max(bytes, 1536L * 1024 * 1024);
            return (int)Math.Min(int.MaxValue, bytes / 1024);
        }

        public static void StartTray(string installDir)
        {
            string exe = ControlExe(installDir);
            if (!File.Exists(exe)) return;
            ProcessStartInfo psi = new ProcessStartInfo(exe, "/tray");
            psi.UseShellExecute = false;
            psi.WorkingDirectory = installDir;
            Process.Start(psi);
        }

        /// <summary>Deletes a file once this process has exited (used by the temporary uninstaller copy).</summary>
        public static void DeleteAfterExit(string path)
        {
            try
            {
                string cmd = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe");
                ProcessStartInfo psi = new ProcessStartInfo(cmd,
                    "/d /c ping -n 4 127.0.0.1 >nul & del /f /q \"" + path + "\"");
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                Process.Start(psi);
            }
            catch (Exception)
            {
                const int MOVEFILE_DELAY_UNTIL_REBOOT = 4;
                NativeMethods.MoveFileEx(path, null, MOVEFILE_DELAY_UNTIL_REBOOT);
            }
        }

        static void CreateLink(string linkPath, string target, string arguments, string workingDir, string icon, string description)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(linkPath));
            IShellLinkW link = (IShellLinkW)new ShellLinkCoClass();
            try
            {
                link.SetPath(target);
                link.SetArguments(arguments);
                link.SetWorkingDirectory(workingDir);
                link.SetIconLocation(icon, 0);
                link.SetDescription(description);
                ((IPersistFile)link).Save(linkPath, true);
            }
            finally
            {
                Marshal.FinalReleaseComObject(link);
            }
        }

        [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
        class ShellLinkCoClass
        {
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
        interface IShellLinkW
        {
            void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cchMaxPath, IntPtr pfd, uint fFlags);
            void GetIDList(out IntPtr ppidl);
            void SetIDList(IntPtr pidl);
            void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cchMaxName);
            void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
            void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cchMaxPath);
            void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
            void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cchMaxPath);
            void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
            void GetHotkey(out short pwHotkey);
            void SetHotkey(short wHotkey);
            void GetShowCmd(out int piShowCmd);
            void SetShowCmd(int iShowCmd);
            void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cchIconPath, out int piIcon);
            void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
            void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, int dwReserved);
            void Resolve(IntPtr hwnd, int fFlags);
            void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
        }
    }
}
