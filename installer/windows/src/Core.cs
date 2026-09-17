// Non-UI logic: build metadata, options, install discovery, PC checks, running PowerShell scripts.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using System.Net;
using System.Net.NetworkInformation;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace DeployerSetup
{
    static class AppInfo
    {
        public const string ControlExeName = "DeployerControl.exe";
        public const string OptionsFileName = "setup-options.json";
        public const string UninstallKeyPath = @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Deployer";

        static string Metadata(string key, string fallback)
        {
            foreach (object a in Assembly.GetExecutingAssembly().GetCustomAttributes(typeof(AssemblyMetadataAttribute), false))
            {
                AssemblyMetadataAttribute m = (AssemblyMetadataAttribute)a;
                if (m.Key == key && !string.IsNullOrEmpty(m.Value)) return m.Value;
            }
            return fallback;
        }

        public static string Version
        {
            get
            {
                object[] attrs = Assembly.GetExecutingAssembly().GetCustomAttributes(typeof(AssemblyInformationalVersionAttribute), false);
                if (attrs.Length > 0) return ((AssemblyInformationalVersionAttribute)attrs[0]).InformationalVersion;
                return Assembly.GetExecutingAssembly().GetName().Version.ToString(3);
            }
        }

        public static string Repo { get { return Metadata("DeployerRepo", "nyx-ulrix/deployer"); } }
        public static string Ref { get { return Metadata("DeployerRef", "v" + Version); } }
        public static string RepoUrl { get { return "https://github.com/" + Repo; } }
        public static string TroubleshootingUrl { get { return RepoUrl + "#troubleshooting"; } }
        public static string ExePath { get { return Application.ExecutablePath; } }
        public static string DefaultInstallDir
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Deployer"); }
        }
        public static string PowerShellExe
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe"); }
        }
    }

    static class Json
    {
        public static object Parse(string text)
        {
            JavaScriptSerializer s = new JavaScriptSerializer();
            s.MaxJsonLength = 16 * 1024 * 1024;
            return s.DeserializeObject(text);
        }

        public static string Write(object value)
        {
            return new JavaScriptSerializer().Serialize(value);
        }

        public static string Str(IDictionary<string, object> d, string key)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return "";
            return Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture);
        }

        public static bool Bool(IDictionary<string, object> d, string key)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return false;
            if (v is bool) return (bool)v;
            bool b;
            return bool.TryParse(Convert.ToString(v), out b) && b;
        }

        public static int Int(IDictionary<string, object> d, string key, int fallback)
        {
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return fallback;
            int i;
            return int.TryParse(Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture), out i) ? i : fallback;
        }

        public static List<IDictionary<string, object>> List(IDictionary<string, object> d, string key)
        {
            List<IDictionary<string, object>> list = new List<IDictionary<string, object>>();
            object v;
            if (d == null || !d.TryGetValue(key, out v) || v == null) return list;
            IEnumerable items = v as IEnumerable;
            if (items == null || v is string) return list;
            foreach (object o in items)
            {
                IDictionary<string, object> item = o as IDictionary<string, object>;
                if (item != null) list.Add(item);
            }
            return list;
        }
    }

    class SetupOptions
    {
        public string Runtime { get; set; }
        public string InstallDir { get; set; }
        public int Port { get; set; }
        public bool EnableLan { get; set; }
        public bool KeepAwake { get; set; }
        public bool Autostart { get; set; }
        public bool DesktopShortcut { get; set; }

        public SetupOptions()
        {
            Runtime = "wsl-engine";
            InstallDir = AppInfo.DefaultInstallDir;
            Port = 8080;
            Autostart = true;
            DesktopShortcut = true;
        }

        public void Save(string path)
        {
            File.WriteAllText(path, Json.Write(this), new UTF8Encoding(false));
        }

        public static SetupOptions Load(string path)
        {
            return new JavaScriptSerializer().Deserialize<SetupOptions>(File.ReadAllText(path));
        }
    }

    static class InstallLocator
    {
        /// <summary>Returns the folder of an existing installation (it has runtime.json), or null.</summary>
        public static string Find()
        {
            List<string> candidates = new List<string>();
            string exeDir = Path.GetDirectoryName(AppInfo.ExePath);
            if (string.Equals(Path.GetFileName(AppInfo.ExePath), AppInfo.ControlExeName, StringComparison.OrdinalIgnoreCase))
                candidates.Add(exeDir);
            string registered = RegisteredInstallDir();
            if (!string.IsNullOrEmpty(registered)) candidates.Add(registered);
            candidates.Add(AppInfo.DefaultInstallDir);
            foreach (string c in candidates)
            {
                try
                {
                    if (File.Exists(Path.Combine(c, "runtime.json"))) return c.TrimEnd('\\');
                }
                catch (Exception)
                {
                }
            }
            return null;
        }

        public static string RegisteredInstallDir()
        {
            try
            {
                using (RegistryKey hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                using (RegistryKey key = hklm.OpenSubKey(AppInfo.UninstallKeyPath))
                {
                    if (key != null) return key.GetValue("InstallLocation") as string;
                }
            }
            catch (Exception)
            {
            }
            return null;
        }

        public static Dictionary<string, string> ReadEnv(string installDir)
        {
            Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                string path = Path.Combine(installDir, ".env");
                if (!File.Exists(path)) return values;
                foreach (string line in File.ReadAllLines(path))
                {
                    string t = line.Trim();
                    if (t.Length == 0 || t.StartsWith("#")) continue;
                    int eq = t.IndexOf('=');
                    if (eq > 0) values[t.Substring(0, eq).Trim()] = t.Substring(eq + 1).Trim();
                }
            }
            catch (Exception)
            {
            }
            return values;
        }

        public static int ReadPort(string installDir)
        {
            string v;
            int port;
            if (ReadEnv(installDir).TryGetValue("DEPLOYER_HTTP_PORT", out v) && int.TryParse(v, out port)) return port;
            return 8080;
        }
    }

    class CheckResult
    {
        public string Id;
        public CheckStatus Status;
        public string Title;
        public string Detail;
        public string LinkText;
        public string LinkUrl;
        public bool Blocking;

        public CheckResult(string id, CheckStatus status, string title, string detail)
        {
            Id = id;
            Status = status;
            Title = title;
            Detail = detail;
            Blocking = status == CheckStatus.Fail;
        }

        public CheckResult Link(string text, string url)
        {
            LinkText = text;
            LinkUrl = url;
            return this;
        }
    }

    class SystemReport
    {
        public readonly List<CheckResult> Items = new List<CheckResult>();
        public bool DockerWorks;
        public string DockerVersion = "";
        public bool DockerDesktopInstalled;
        public int SuggestedPort = 8080;
        public bool Done;

        public bool HasBlocking { get { return Items.Any(i => i.Blocking); } }
        public bool HasWarnings { get { return Items.Any(i => i.Status == CheckStatus.Warn || i.Status == CheckStatus.Fail); } }

        public CheckResult Get(string id)
        {
            return Items.FirstOrDefault(i => i.Id == id);
        }
    }

    static class SystemChecks
    {
        public const string VirtualizationHelpUrl = "https://support.microsoft.com/windows/enable-virtualization-on-windows-c5578302-6e43-4b4b-a449-8ced115f58e1";
        public const string AtlasUrl = "https://www.mongodb.com/atlas";

        public static readonly string[] Ids = { "windows", "virtualization", "memory", "disk", "avx", "port", "internet" };

        public static string TitleFor(string id)
        {
            switch (id)
            {
                case "windows": return "Windows version";
                case "virtualization": return "Virtualization";
                case "memory": return "Memory";
                case "disk": return "Free disk space";
                case "avx": return "Processor features";
                case "port": return "Network port";
                default: return "Internet connection";
            }
        }

        public static SystemReport Run(string installDir, int port, int installedPort, bool includeInternet)
        {
            SystemReport report = new SystemReport();
            DetectDocker(report);

            // Windows version
            int build = 0;
            string display = "";
            try
            {
                using (RegistryKey hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                using (RegistryKey k = hklm.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
                {
                    if (k != null)
                    {
                        int.TryParse(Convert.ToString(k.GetValue("CurrentBuildNumber")), out build);
                        display = Convert.ToString(k.GetValue("DisplayVersion") ?? k.GetValue("ReleaseId") ?? "");
                    }
                }
            }
            catch (Exception)
            {
            }
            if (build == 0) build = Environment.OSVersion.Version.Build;
            string winName = (build >= 22000 ? "Windows 11" : "Windows 10") + (display.Length > 0 ? " " + display : "");
            if (!Environment.Is64BitOperatingSystem)
            {
                report.Items.Add(new CheckResult("windows", CheckStatus.Fail, "32-bit Windows can't run Deployer",
                    "Deployer needs 64-bit Windows 10 (version 2004 or newer) or Windows 11."));
            }
            else if (build < 19041)
            {
                report.Items.Add(new CheckResult("windows", CheckStatus.Fail, "Windows is too old (build " + build + ")",
                    "Open Settings > Windows Update and install the latest updates (Windows 10 version 2004 or newer), then run this setup again."));
            }
            else
            {
                report.Items.Add(new CheckResult("windows", CheckStatus.Ok, winName + " (64-bit) is supported", null));
            }
            bool arm = string.Equals(Environment.GetEnvironmentVariable("PROCESSOR_ARCHITECTURE"), "ARM64", StringComparison.OrdinalIgnoreCase)
                       || string.Equals(Environment.GetEnvironmentVariable("PROCESSOR_ARCHITEW6432"), "ARM64", StringComparison.OrdinalIgnoreCase);

            // Virtualization
            bool? firmware = null;
            bool hypervisor = false;
            try
            {
                using (ManagementObjectSearcher s = new ManagementObjectSearcher("SELECT VirtualizationFirmwareEnabled FROM Win32_Processor"))
                {
                    foreach (ManagementBaseObject o in s.Get())
                    {
                        object v = o["VirtualizationFirmwareEnabled"];
                        if (v != null) firmware = (firmware ?? false) || (bool)v;
                    }
                }
                using (ManagementObjectSearcher s = new ManagementObjectSearcher("SELECT HypervisorPresent FROM Win32_ComputerSystem"))
                {
                    foreach (ManagementBaseObject o in s.Get())
                    {
                        object v = o["HypervisorPresent"];
                        if (v != null) hypervisor |= (bool)v;
                    }
                }
            }
            catch (Exception)
            {
            }
            if (firmware == true || hypervisor)
            {
                report.Items.Add(new CheckResult("virtualization", CheckStatus.Ok, "Virtualization is turned on", null));
            }
            else if (report.DockerWorks)
            {
                report.Items.Add(new CheckResult("virtualization", CheckStatus.Warn, "Virtualization looks turned off",
                    "Docker is already running here, so you can use it. The free Docker Engine and Docker Desktop need virtualization turned on in your PC's BIOS/UEFI.")
                    .Link("How to turn on virtualization", VirtualizationHelpUrl));
            }
            else
            {
                report.Items.Add(new CheckResult("virtualization", CheckStatus.Fail, "Virtualization is turned off",
                    "Restart the PC, open its BIOS/UEFI setup (usually F2, F10, Del or Esc while it starts) and turn on \"Intel Virtualization Technology\" (VT-x) or \"SVM Mode\" (AMD). Then run this setup again.")
                    .Link("How to turn on virtualization", VirtualizationHelpUrl));
            }

            // Memory
            double ramGb = 0;
            try
            {
                NativeMethods.MEMORYSTATUSEX m = new NativeMethods.MEMORYSTATUSEX();
                m.dwLength = (uint)System.Runtime.InteropServices.Marshal.SizeOf(typeof(NativeMethods.MEMORYSTATUSEX));
                if (NativeMethods.GlobalMemoryStatusEx(ref m)) ramGb = m.ullTotalPhys / 1073741824.0;
            }
            catch (Exception)
            {
            }
            string ramText = Math.Round(ramGb, ramGb < 10 ? 1 : 0).ToString(System.Globalization.CultureInfo.CurrentCulture) + " GB";
            if (ramGb <= 0)
                report.Items.Add(new CheckResult("memory", CheckStatus.Warn, "Couldn't read the amount of memory", "Deployer needs at least 4 GB of memory (8 GB recommended)."));
            else if (ramGb < 3.6)
                report.Items.Add(new CheckResult("memory", CheckStatus.Warn, "Only " + ramText + " of memory",
                    "Deployer may be slow. 4 GB is the minimum and 8 GB is recommended. Closing other apps helps."));
            else if (ramGb < 7.5)
                report.Items.Add(new CheckResult("memory", CheckStatus.Ok, ramText + " of memory (enough; 8 GB is better for many projects)", null));
            else
                report.Items.Add(new CheckResult("memory", CheckStatus.Ok, ramText + " of memory", null));

            // Disk
            try
            {
                string root = Path.GetPathRoot(Path.GetFullPath(installDir));
                DriveInfo drive = new DriveInfo(root);
                double freeGb = drive.AvailableFreeSpace / 1073741824.0;
                string driveName = root.TrimEnd('\\');
                string freeText = Math.Round(freeGb, freeGb < 10 ? 1 : 0) + " GB free on " + driveName;
                if (freeGb < 4)
                    report.Items.Add(new CheckResult("disk", CheckStatus.Fail, "Not enough free space: " + freeText,
                        "Deployer needs about 10 GB. Free up space (Settings > System > Storage) or choose a different drive on the Options page."));
                else if (freeGb < 10)
                    report.Items.Add(new CheckResult("disk", CheckStatus.Warn, "Only " + freeText,
                        "About 10 GB is recommended for Deployer and your databases. You can choose another drive on the Options page."));
                else
                    report.Items.Add(new CheckResult("disk", CheckStatus.Ok, freeText, null));
            }
            catch (Exception)
            {
                report.Items.Add(new CheckResult("disk", CheckStatus.Warn, "Couldn't check free disk space", "About 10 GB is recommended."));
            }

            // AVX
            bool avx = false;
            try
            {
                avx = NativeMethods.IsProcessorFeaturePresent(39);
            }
            catch (Exception)
            {
            }
            if (avx)
                report.Items.Add(new CheckResult("avx", CheckStatus.Ok, "Your processor can run MongoDB (AVX)", null));
            else
                report.Items.Add(new CheckResult("avx", CheckStatus.Warn, "Your processor can't run MongoDB on this PC (no AVX)",
                    "Everything else works. Projects can still use an external MongoDB, such as a free MongoDB Atlas cluster.")
                    .Link("About MongoDB Atlas", AtlasUrl));
            if (arm)
                report.Items.Add(new CheckResult("arch", CheckStatus.Warn, "ARM processor detected",
                    "Deployer's ready-made images are for Intel/AMD PCs, so setup builds them itself. This can take 30 minutes or more."));

            // Port
            report.SuggestedPort = port;
            if (port == installedPort)
            {
                report.Items.Add(new CheckResult("port", CheckStatus.Ok, "Port " + port + " belongs to your existing Deployer", null));
            }
            else if (Ports.IsFree(port))
            {
                report.Items.Add(new CheckResult("port", CheckStatus.Ok, "Port " + port + " is free", null));
            }
            else
            {
                report.SuggestedPort = Ports.SuggestFree(port);
                report.Items.Add(new CheckResult("port", CheckStatus.Warn, "Port " + port + " is used by another program",
                    "No problem: Deployer will use port " + report.SuggestedPort + " instead. You can change it on the Options page."));
            }

            // Internet
            if (includeInternet)
            {
                string error;
                if (Internet.CanReach("https://github.com/", out error))
                    report.Items.Add(new CheckResult("internet", CheckStatus.Ok, "Connected to the internet", null));
                else
                    report.Items.Add(new CheckResult("internet", CheckStatus.Fail, "Can't reach github.com",
                        "Setup downloads Deployer and Docker (about 1-2 GB). Check your internet connection, VPN or proxy, then click Check again."));
            }

            report.Done = true;
            return report;
        }

        public static void DetectDocker(SystemReport report)
        {
            string desktop1 = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Docker\Docker\Docker Desktop.exe");
            string desktop2 = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\DockerDesktop\Docker Desktop.exe");
            report.DockerDesktopInstalled = File.Exists(desktop1) || File.Exists(desktop2);
            string docker = FindDocker();
            if (docker == null) return;
            ProcessResult r = ProcessUtil.Run(docker, "info --format {{.ServerVersion}}", 25000);
            string v = r.StdOut.Trim();
            if (r.ExitCode == 0 && v.Length > 0 && char.IsDigit(v[0]))
            {
                report.DockerWorks = true;
                report.DockerVersion = v;
            }
        }

        public static string FindDocker()
        {
            string path = Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach (string dir in path.Split(';'))
            {
                try
                {
                    if (dir.Trim().Length == 0) continue;
                    string candidate = Path.Combine(Environment.ExpandEnvironmentVariables(dir.Trim().Trim('"')), "docker.exe");
                    if (File.Exists(candidate)) return candidate;
                }
                catch (Exception)
                {
                }
            }
            string[] known =
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Docker\Docker\resources\bin\docker.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\DockerDesktop\resources\bin\docker.exe")
            };
            return known.FirstOrDefault(File.Exists);
        }
    }

    static class Ports
    {
        public static bool IsFree(int port)
        {
            try
            {
                IPGlobalProperties props = IPGlobalProperties.GetIPGlobalProperties();
                return !props.GetActiveTcpListeners().Any(e => e.Port == port);
            }
            catch (Exception)
            {
                return true;
            }
        }

        public static int SuggestFree(int start)
        {
            int[] preferred = { 8080, 8090, 8081, 8088, 8888, 8000, 3080 };
            foreach (int p in preferred) if (p != start && IsFree(p)) return p;
            for (int p = 8081; p < 8999; p++) if (IsFree(p)) return p;
            return start;
        }
    }

    static class Internet
    {
        public static bool CanReach(string url, out string error)
        {
            error = null;
            try
            {
                ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
                req.Method = "HEAD";
                req.Timeout = 8000;
                req.UserAgent = "DeployerSetup";
                req.AllowAutoRedirect = false;
                using (req.GetResponse())
                {
                }
                return true;
            }
            catch (WebException ex)
            {
                if (ex.Response != null)
                {
                    ex.Response.Close();
                    return true;
                }
                error = ex.Message;
                return false;
            }
            catch (Exception ex)
            {
                error = ex.Message;
                return false;
            }
        }

        /// <summary>GET http://127.0.0.1:port/v1/health. Local only.</summary>
        public static bool Health(int port, out string body)
        {
            body = "";
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/v1/health");
                req.Timeout = 3000;
                req.ReadWriteTimeout = 3000;
                req.Proxy = null;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (StreamReader sr = new StreamReader(resp.GetResponseStream()))
                {
                    body = sr.ReadToEnd();
                    return resp.StatusCode == HttpStatusCode.OK;
                }
            }
            catch (Exception)
            {
                return false;
            }
        }
    }

    class ProcessResult
    {
        public int ExitCode = -1;
        public string StdOut = "";
        public string StdErr = "";
    }

    static class ProcessUtil
    {
        public static string Quote(string arg)
        {
            if (arg == null) arg = "";
            if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return arg;
            StringBuilder sb = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in arg)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') sb.Append('\\', slashes * 2 + 1);
                else if (slashes > 0) sb.Append('\\', slashes);
                sb.Append(c);
                slashes = 0;
            }
            if (slashes > 0) sb.Append('\\', slashes * 2);
            sb.Append('"');
            return sb.ToString();
        }

        public static string JoinArgs(IEnumerable<string> args)
        {
            return string.Join(" ", args.Select(Quote).ToArray());
        }

        public static ProcessResult Run(string file, string arguments, int timeoutMs)
        {
            ProcessResult result = new ProcessResult();
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(file, arguments);
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.StandardOutputEncoding = Encoding.UTF8;
                psi.StandardErrorEncoding = Encoding.UTF8;
                using (Process p = Process.Start(psi))
                {
                    StringBuilder err = new StringBuilder();
                    p.ErrorDataReceived += (s, e) => { if (e.Data != null) lock (err) err.AppendLine(e.Data); };
                    p.BeginErrorReadLine();
                    string outText = "";
                    Thread reader = new Thread(() => { try { outText = p.StandardOutput.ReadToEnd(); } catch (Exception) { } });
                    reader.IsBackground = true;
                    reader.Start();
                    if (!p.WaitForExit(timeoutMs))
                    {
                        KillTree(p.Id);
                        result.ExitCode = -2;
                        result.StdErr = "timed out";
                        return result;
                    }
                    reader.Join(3000);
                    result.ExitCode = p.ExitCode;
                    result.StdOut = outText.Replace("\0", "");
                    lock (err) result.StdErr = err.ToString();
                }
            }
            catch (Exception ex)
            {
                result.StdErr = ex.Message;
            }
            return result;
        }

        public static void KillTree(int pid)
        {
            try
            {
                using (ManagementObjectSearcher s = new ManagementObjectSearcher("SELECT ProcessId FROM Win32_Process WHERE ParentProcessId=" + pid))
                {
                    foreach (ManagementBaseObject o in s.Get())
                    {
                        KillTree(Convert.ToInt32(o["ProcessId"]));
                    }
                }
            }
            catch (Exception)
            {
            }
            try
            {
                using (Process p = Process.GetProcessById(pid)) p.Kill();
            }
            catch (Exception)
            {
            }
        }
    }

    enum MarkerKind { None, Step, Check, RebootRequired, Done, Error, Runtime, Status, Other }

    class Marker
    {
        public MarkerKind Kind;
        public string Text = "";
        public int Step;
        public int Total;
        public string CheckId = "";
        public string CheckState = "";
        public readonly Dictionary<string, string> Values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        public const string Prefix = "##deployer:";

        public static Marker Parse(string line)
        {
            if (line == null) return null;
            string t = line.Trim();
            if (!t.StartsWith(Prefix, StringComparison.Ordinal)) return null;
            string body = t.Substring(Prefix.Length);
            int sp = body.IndexOf(' ');
            string kind = sp < 0 ? body : body.Substring(0, sp);
            string rest = sp < 0 ? "" : body.Substring(sp + 1).Trim();
            Marker m = new Marker();
            m.Text = rest;
            switch (kind)
            {
                case "step":
                    {
                        m.Kind = MarkerKind.Step;
                        int sp2 = rest.IndexOf(' ');
                        string frac = sp2 < 0 ? rest : rest.Substring(0, sp2);
                        m.Text = sp2 < 0 ? "" : rest.Substring(sp2 + 1).Trim();
                        string[] parts = frac.Split('/');
                        if (parts.Length != 2 || !int.TryParse(parts[0], out m.Step) || !int.TryParse(parts[1], out m.Total)) m.Kind = MarkerKind.Other;
                        break;
                    }
                case "check":
                    {
                        m.Kind = MarkerKind.Check;
                        string[] parts = rest.Split(new[] { ' ' }, 3);
                        if (parts.Length >= 2)
                        {
                            m.CheckId = parts[0];
                            m.CheckState = parts[1];
                            m.Text = parts.Length > 2 ? parts[2] : "";
                        }
                        break;
                    }
                case "reboot-required": m.Kind = MarkerKind.RebootRequired; break;
                case "error": m.Kind = MarkerKind.Error; break;
                case "runtime": m.Kind = MarkerKind.Runtime; break;
                case "status": m.Kind = MarkerKind.Status; break;
                case "done":
                    m.Kind = MarkerKind.Done;
                    foreach (string pair in rest.Split(' '))
                    {
                        int eq = pair.IndexOf('=');
                        if (eq > 0) m.Values[pair.Substring(0, eq)] = pair.Substring(eq + 1);
                    }
                    break;
                default: m.Kind = MarkerKind.Other; break;
            }
            return m;
        }
    }

    /// <summary>Runs powershell.exe -File script and streams its output line by line.</summary>
    class ScriptRunner
    {
        Process process;
        int readersLeft;
        readonly object gate = new object();
        public event Action<string> OutputLine;
        public event Action<string> TransientLine;
        public event Action<int> Exited;
        public bool IsRunning { get; private set; }
        public bool Cancelled { get; private set; }

        public static List<string> ScriptArgs(string scriptPath, IEnumerable<string> args)
        {
            List<string> all = new List<string> { "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath };
            all.AddRange(args);
            return all;
        }

        public void Start(string scriptPath, IEnumerable<string> args)
        {
            ProcessStartInfo psi = new ProcessStartInfo(AppInfo.PowerShellExe, ProcessUtil.JoinArgs(ScriptArgs(scriptPath, args)));
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.RedirectStandardInput = true;
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.StandardErrorEncoding = Encoding.UTF8;
            psi.WorkingDirectory = Path.GetTempPath();
            process = new Process();
            process.StartInfo = psi;
            process.Start();
            IsRunning = true;
            try { process.StandardInput.Close(); } catch (Exception) { }
            readersLeft = 2;
            StartReader(process.StandardOutput);
            StartReader(process.StandardError);
            // Wait for the process itself, not for its pipes: a detached grandchild (e.g. the WSL
            // keep-alive started by "deployer start") may keep the pipes open long after.
            Thread waiter = new Thread(WaitLoop);
            waiter.IsBackground = true;
            waiter.Start();
        }

        void WaitLoop()
        {
            int code = -1;
            try
            {
                while (!process.WaitForExit(500))
                {
                }
                code = process.ExitCode;
            }
            catch (Exception)
            {
            }
            lock (gate)
            {
                if (readersLeft > 0) Monitor.Wait(gate, 3000);
            }
            IsRunning = false;
            if (Exited != null) Exited(code);
        }

        void StartReader(StreamReader reader)
        {
            Thread t = new Thread(() => ReadLoop(reader));
            t.IsBackground = true;
            t.Start();
        }

        void ReadLoop(StreamReader reader)
        {
            StringBuilder line = new StringBuilder();
            bool pendingCr = false;
            char[] buf = new char[4096];
            try
            {
                int n;
                while ((n = reader.Read(buf, 0, buf.Length)) > 0)
                {
                    for (int i = 0; i < n; i++)
                    {
                        char c = buf[i];
                        if (c == '\0') continue;
                        if (pendingCr)
                        {
                            pendingCr = false;
                            if (c == '\n') { Emit(line, false); continue; }
                            Emit(line, true);
                        }
                        if (c == '\r') { pendingCr = true; continue; }
                        if (c == '\n') { Emit(line, false); continue; }
                        line.Append(c);
                    }
                }
            }
            catch (Exception)
            {
            }
            if (line.Length > 0) Emit(line, false);
            lock (gate)
            {
                readersLeft--;
                if (readersLeft == 0) Monitor.PulseAll(gate);
            }
        }

        void Emit(StringBuilder line, bool transient)
        {
            string text = line.ToString();
            line.Length = 0;
            lock (gate)
            {
                if (transient)
                {
                    if (TransientLine != null && text.Trim().Length > 0) TransientLine(text);
                }
                else if (OutputLine != null)
                {
                    OutputLine(text);
                }
            }
        }

        public void Cancel()
        {
            Cancelled = true;
            try
            {
                if (process != null && !process.HasExited) ProcessUtil.KillTree(process.Id);
            }
            catch (Exception)
            {
            }
        }
    }

    /// <summary>The installer scripts and deploy files embedded in the exe (resources named payload/...).</summary>
    static class Payload
    {
        const string Prefix = "payload/";

        public static string[] Names()
        {
            return Assembly.GetExecutingAssembly().GetManifestResourceNames().Where(n => n.StartsWith(Prefix)).OrderBy(n => n).ToArray();
        }

        public static string Extract()
        {
            string root = Path.Combine(Path.GetTempPath(), "DeployerSetup-" + Guid.NewGuid().ToString("N").Substring(0, 10));
            Assembly asm = Assembly.GetExecutingAssembly();
            foreach (string name in Names())
            {
                string rel = name.Substring(Prefix.Length).Replace('/', Path.DirectorySeparatorChar);
                string target = Path.Combine(root, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                using (Stream s = asm.GetManifestResourceStream(name))
                using (FileStream f = File.Create(target))
                {
                    s.CopyTo(f);
                }
            }
            return root;
        }

        public static void Cleanup(string root)
        {
            if (string.IsNullOrEmpty(root)) return;
            try
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
            catch (Exception)
            {
            }
        }
    }

    /// <summary>Finds deployer.ps1 for an installation, preferring the installed copy.</summary>
    static class DeployerCli
    {
        public static string ScriptFor(string installDir, ref string extractedRoot)
        {
            string installed = Path.Combine(installDir ?? "", @"installer\deployer.ps1");
            if (installDir != null && File.Exists(installed) && File.Exists(Path.Combine(installDir, @"installer\lib\common.ps1")))
                return installed;
            if (extractedRoot == null) extractedRoot = Payload.Extract();
            return Path.Combine(extractedRoot, @"installer\deployer.ps1");
        }
    }
}
