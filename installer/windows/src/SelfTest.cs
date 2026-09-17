// /selftest <outdir>: renders every wizard page, the control window and dialogs to PNG at 100 % and
// 150 %, checks marker parsing, and drives the wizard through a real "install.ps1 -DryRun".
// Needs no administrator rights (CI uses DeployerSetup.selftest.exe, built with an asInvoker manifest).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace DeployerSetup
{
    static class SelfTest
    {
        static readonly StringBuilder report = new StringBuilder();
        static int failures;
        static int images;

        const int WatchdogSeconds = 60;
        static WizardForm liveWizard;

        public static int Run(string outDir)
        {
            Directory.CreateDirectory(outDir);
            StartWatchdog(outDir);
            Line("Deployer Setup " + AppInfo.Version + " self-test (" + AppInfo.Repo + " @ " + AppInfo.Ref + ")");
            Line("Embedded files: " + string.Join(", ", Payload.Names()));
            Check(Payload.Names().Any(n => n.EndsWith("installer/install.ps1")), "install.ps1 is embedded");
            Check(Payload.Names().Any(n => n.EndsWith("installer/lib/common.ps1")), "lib/common.ps1 is embedded");
            Check(Payload.Names().Any(n => n.EndsWith("deploy/docker-compose.yml")), "docker-compose.yml is embedded");
            TestMarkers();

            foreach (float scale in new[] { 1f, 1.5f })
            {
                string dir = Path.Combine(outDir, scale == 1f ? "100" : "150");
                Directory.CreateDirectory(dir);
                RenderAll(dir, scale);
            }

            LiveDryRun(outDir);

            Line("");
            Line(images + " images rendered, " + failures + " failure(s).");
            File.WriteAllText(Path.Combine(outDir, "selftest-report.txt"), report.ToString());
            Console.WriteLine(report.ToString());
            return failures == 0 ? 0 : 1;
        }

        /// <summary>Whatever happens (a hang, a stuck PowerShell), the self-test ends after 60 seconds.</summary>
        static void StartWatchdog(string outDir)
        {
            Thread t = new Thread(() =>
            {
                Thread.Sleep(WatchdogSeconds * 1000);
                try
                {
                    WizardForm w = liveWizard;
                    if (w != null && w.runner != null) w.runner.Cancel();
                    lock (report)
                    {
                        report.AppendLine("FAIL  watchdog: self-test did not finish within " + WatchdogSeconds + " s");
                        File.WriteAllText(Path.Combine(outDir, "selftest-report.txt"), report.ToString());
                    }
                }
                catch (Exception)
                {
                }
                Environment.Exit(2);
            });
            t.IsBackground = true;
            t.Start();
        }

        static void Line(string text)
        {
            lock (report) report.AppendLine(text);
        }

        static void Check(bool ok, string what)
        {
            Line((ok ? "PASS  " : "FAIL  ") + what);
            if (!ok) failures++;
        }

        static void TestMarkers()
        {
            Marker m = Marker.Parse("##deployer:step 3/10 Installing the free Docker Engine (WSL2)");
            Check(m != null && m.Kind == MarkerKind.Step && m.Step == 3 && m.Total == 10 && m.Text == "Installing the free Docker Engine (WSL2)", "step marker parses");
            m = Marker.Parse("##deployer:done url=http://localhost:8090 dryrun=true");
            Check(m != null && m.Kind == MarkerKind.Done && m.Values["url"] == "http://localhost:8090", "done marker parses");
            m = Marker.Parse("##deployer:check port fail Port 8080 is already used by: nginx.");
            Check(m != null && m.Kind == MarkerKind.Check && m.CheckId == "port" && m.CheckState == "fail", "check marker parses");
            Check(Marker.Parse("##deployer:reboot-required").Kind == MarkerKind.RebootRequired, "reboot marker parses");
            Check(Marker.Parse("##deployer:error Something broke").Text == "Something broke", "error marker parses");
            Check(Marker.Parse("    [ok] not a marker") == null, "plain output is not a marker");
            Check(ProcessUtil.Quote(@"C:\Program Files\Deployer\") == "\"C:\\Program Files\\Deployer\\\\\"", "argument quoting doubles trailing backslashes");
        }

        /// <summary>Renders a form that is never shown: handles are created, nothing appears on screen.</summary>
        static void Save(ThemedForm form, string dir, string name)
        {
            try
            {
                form.ShowInTaskbar = false;
                form.StartPosition = FormStartPosition.Manual;
                form.Location = new Point(-32000, -32000);
                CreateHandles(form);
                using (Bitmap bmp = form.RenderClient())
                {
                    bmp.Save(Path.Combine(dir, name + ".png"), ImageFormat.Png);
                }
                images++;
                Line("IMG   " + Path.GetFileName(dir) + "/" + name + ".png (" + form.ClientSize.Width + "x" + form.ClientSize.Height + ")");
                CheckOverflow(form, dir, name);
            }
            catch (Exception ex)
            {
                Check(false, "render " + name + ": " + ex.Message);
            }
            finally
            {
                // Dispose without Close(): no FormClosing prompts, and the form was never visible.
                form.Dispose();
            }
        }

        static void CreateHandles(Control c)
        {
            IntPtr h = c.Handle;
            GC.KeepAlive(h);
            foreach (Control child in c.Controls) CreateHandles(child);
        }

        /// <summary>Flags controls that stick out of their parent (clipped text or buttons).</summary>
        static void CheckOverflow(Control root, string dir, string name)
        {
            List<string> problems = new List<string>();
            Walk(root, problems);
            if (problems.Count > 0) Check(false, Path.GetFileName(dir) + "/" + name + " layout: " + string.Join("; ", problems.Take(5)));
        }

        static void Walk(Control parent, List<string> problems)
        {
            foreach (Control c in parent.Controls)
            {
                if (c is TextBox || c is ComboBox) continue;
                Panel scroller = parent as Panel;
                bool scrolls = scroller != null && scroller.AutoScroll;
                if (!scrolls && !(parent is TextBox) && (c.Right > parent.ClientSize.Width + 1 || c.Bottom > parent.ClientSize.Height + 1 || c.Left < 0 || c.Top < 0))
                {
                    problems.Add(c.GetType().Name + " '" + Short(c.Text) + "' outside " + parent.GetType().Name + " (" + c.Bounds + " in " + parent.ClientSize + ")");
                }
                if (scrolls && (c.Right > parent.ClientSize.Width + 1 || c.Bottom > parent.ClientSize.Height + 1))
                {
                    problems.Add("page content needs scrolling: " + c.GetType().Name + " '" + Short(c.Text) + "' at " + c.Bounds + " in " + parent.ClientSize);
                }
                Walk(c, problems);
            }
        }

        static string Short(string s)
        {
            if (s == null) return "";
            return s.Length > 30 ? s.Substring(0, 30) + "..." : s;
        }

        static WizardForm Wizard(float scale, bool dryRun)
        {
            WizardForm w = new WizardForm(dryRun, false, scale, true);
            w.installedDir = null;
            w.installedPort = -1;
            w.options = new SetupOptions();
            w.options.Port = Ports.IsFree(8080) ? 8080 : Ports.SuggestFree(8080);
            return w;
        }

        static SystemReport SampleReport(int variant)
        {
            SystemReport r = new SystemReport();
            r.Done = true;
            r.DockerDesktopInstalled = variant == 1;
            r.DockerWorks = variant == 1;
            r.DockerVersion = "27.3.1";
            r.SuggestedPort = 8080;
            r.Items.Add(new CheckResult("windows", CheckStatus.Ok, "Windows 11 24H2 (64-bit) is supported", null));
            if (variant == 2)
            {
                r.Items.Add(new CheckResult("virtualization", CheckStatus.Fail, "Virtualization is turned off",
                    "Restart the PC, open its BIOS/UEFI setup (usually F2, F10, Del or Esc while it starts) and turn on \"Intel Virtualization Technology\" (VT-x) or \"SVM Mode\" (AMD). Then run this setup again.")
                    .Link("How to turn on virtualization", SystemChecks.VirtualizationHelpUrl));
                r.Items.Add(new CheckResult("memory", CheckStatus.Warn, "Only 3.9 GB of memory", "Deployer may be slow. 4 GB is the minimum and 8 GB is recommended. Closing other apps helps."));
            }
            else
            {
                r.Items.Add(new CheckResult("virtualization", CheckStatus.Ok, "Virtualization is turned on", null));
                r.Items.Add(new CheckResult("memory", CheckStatus.Ok, "8 GB of memory", null));
            }
            r.Items.Add(new CheckResult("disk", CheckStatus.Ok, "212 GB free on C:", null));
            if (variant == 0)
                r.Items.Add(new CheckResult("avx", CheckStatus.Ok, "Your processor can run MongoDB (AVX)", null));
            else
                r.Items.Add(new CheckResult("avx", CheckStatus.Warn, "Your processor can't run MongoDB on this PC (no AVX)",
                    "Everything else works. Projects can still use an external MongoDB, such as a free MongoDB Atlas cluster.")
                    .Link("About MongoDB Atlas", SystemChecks.AtlasUrl));
            if (variant == 1)
                r.Items.Add(new CheckResult("port", CheckStatus.Warn, "Port 8080 is used by another program",
                    "No problem: Deployer will use port 8090 instead. You can change it on the Options page."));
            else
                r.Items.Add(new CheckResult("port", CheckStatus.Ok, "Port 8080 is free", null));
            r.Items.Add(new CheckResult("internet", CheckStatus.Ok, "Connected to the internet", null));
            return r;
        }

        static readonly string[] SampleLog =
        {
            "Deployer Setup 0.1.0 - 2026-09-16 10:02:11",
            "==> Checking this PC",
            "    Microsoft Windows 11 Home (build 26100), Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz",
            "    [ok] Windows version is supported",
            "    [ok] Hardware virtualization is enabled",
            "    [ok] 7.9 GB RAM (works; 8 GB recommended for several projects)",
            "    [ok] 212.4 GB free on C:",
            "    [ok] Runtime: wsl-engine",
            "==> Getting Deployer files",
            "    Using the bundled deploy files (v0.1.0)",
            "==> Setting up the free Docker Engine in WSL2",
            "    [ok] WSL 2.4.13.0 is ready",
            "    Downloading Ubuntu 24.04 for WSL (~380 MB) from https://releases.ubuntu.com/noble/ubuntu-24.04.3-wsl-amd64.wsl",
            "    [ok] SHA256 checksum verified",
            "    Creating WSL distro 'deployer' in C:\\ProgramData\\Deployer\\wsl",
            "[setup-engine] Installing docker-ce, docker-ce-cli, containerd.io, buildx and compose plugins",
            "    [ok] Docker Engine is running in WSL",
            "==> Writing configuration",
            "    [ok] .env created with freshly generated secrets (readable by Administrators, SYSTEM and you only)",
            "==> Downloading container images",
            "    Downloading container images...",
            " mariadb Pulling",
            " redis Pulled"
        };

        static void RenderAll(string dir, float scale)
        {
            WizardForm w;

            w = Wizard(scale, false);
            Save(w, dir, "wizard-1-welcome");

            w = Wizard(scale, false);
            w.page = WizardPage.Checks;
            w.checking = true;
            w.Rebuild();
            Save(w, dir, "wizard-2-checks-running");

            w = Wizard(scale, false);
            w.page = WizardPage.Checks;
            w.ApplyReport(SampleReport(0));
            w.Rebuild();
            Save(w, dir, "wizard-2-checks-ready");

            w = Wizard(scale, false);
            w.page = WizardPage.Checks;
            w.ApplyReport(SampleReport(1));
            w.Rebuild();
            Save(w, dir, "wizard-2-checks-notes");

            w = Wizard(scale, false);
            w.page = WizardPage.Checks;
            w.ApplyReport(SampleReport(2));
            w.Rebuild();
            Save(w, dir, "wizard-2-checks-blocked");

            w = Wizard(scale, false);
            w.ApplyReport(SampleReport(1));
            w.page = WizardPage.Docker;
            w.options.Runtime = "wsl-engine";
            w.Rebuild();
            Save(w, dir, "wizard-3-docker");

            w = Wizard(scale, false);
            w.ApplyReport(SampleReport(0));
            w.options.Port = Ports.IsFree(8080) ? 8080 : Ports.SuggestFree(8080);
            w.page = WizardPage.Options;
            w.Rebuild();
            Save(w, dir, "wizard-4-options");

            w = InstallSample(scale, false);
            Save(w, dir, "wizard-5-install");

            w = InstallSample(scale, true);
            Save(w, dir, "wizard-5-install-details");

            w = Wizard(scale, false);
            w.page = WizardPage.Reboot;
            w.Rebuild();
            Save(w, dir, "wizard-5-restart");

            w = Wizard(scale, false);
            w.page = WizardPage.Error;
            w.errorMessage = "Could not download Deployer 'v0.1.0' from github.com/nyx-ulrix/deployer. Check the -Repo/-Ref values and your internet connection.";
            w.Rebuild();
            Save(w, dir, "wizard-5-error");

            w = Wizard(scale, false);
            w.page = WizardPage.Finish;
            w.doneUrl = "http://localhost:8080";
            w.Rebuild();
            Save(w, dir, "wizard-6-finish");

            w = Wizard(scale, true);
            w.page = WizardPage.Welcome;
            w.Rebuild();
            Save(w, dir, "wizard-testmode-welcome");

            // Deployer Control
            Save(ControlSample(scale, 0), dir, "control-running");
            Save(ControlSample(scale, 1), dir, "control-stopped");
            Save(ControlSample(scale, 2), dir, "control-busy");
            Save(ControlSample(scale, 3), dir, "control-not-responding");

            Save(new SettingsDialog(8080, false, true, true, scale), dir, "dialog-settings");
            Dictionary<string, object> device = new Dictionary<string, object>();
            device["mode"] = "host";
            device["primary_url"] = "https://deployer.example.org";
            device["device_name"] = "Office PC";
            device["connected"] = true;
            Dictionary<string, object> hostedDb = new Dictionary<string, object>();
            hostedDb["database_name"] = "p_shop";
            hostedDb["kind"] = "mariadb";
            device["hosted_sources"] = new object[] { hostedDb };
            Save(ControlForm.CreateDeviceDialog(device, scale), dir, "dialog-device-host");
            Dictionary<string, object> standalone = new Dictionary<string, object>();
            standalone["mode"] = "standalone";
            Save(ControlForm.CreateDeviceDialog(standalone, scale), dir, "dialog-device-standalone");
            UninstallForm u = new UninstallForm(@"C:\ProgramData\Deployer", scale, true);
            Save(u, dir, "dialog-uninstall");
            u = new UninstallForm(@"C:\ProgramData\Deployer", scale, true);
            u.deleteData = true;
            u.Rebuild();
            Save(u, dir, "dialog-uninstall-delete-data");
            u = new UninstallForm(@"C:\ProgramData\Deployer", scale, true);
            u.transient = "Containers removed";
            u.SetPhase(UninstallForm.Phase.Running);
            Save(u, dir, "dialog-uninstall-running");
            u = new UninstallForm(@"C:\ProgramData\Deployer", scale, true);
            u.SetPhase(UninstallForm.Phase.Done);
            Save(u, dir, "dialog-uninstall-done");
            Save(ErrorDialog.Create("Backing up didn't work",
                "mariadb-dump failed (exit code 1). Is the stack running? Click Copy details to share the full output when asking for help.",
                "details", scale), dir, "dialog-error");
            List<DialogButton> buttons = new List<DialogButton>
            {
                new DialogButton("Keep installing", ButtonStyle.Secondary, DialogResult.No),
                new DialogButton("Stop installation", ButtonStyle.Danger, DialogResult.Yes)
            };
            Save(new MessageDialog("Stop the installation?",
                "Deployer isn't fully installed yet. You can run setup again later and it continues where it left off.",
                IconKind.Warn, Theme.Warn, buttons, null, null, scale), dir, "dialog-confirm");

            LogWindow logs = new LogWindow(@"C:\ProgramData\Deployer", scale);
            logs.SetText(string.Join("\r\n", new[]
            {
                "api-1        | INFO:     Started server process [1]",
                "api-1        | INFO:     Waiting for application startup.",
                "api-1        | INFO:     Application startup complete.",
                "api-1        | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)",
                "caddy-1      | {\"level\":\"info\",\"msg\":\"serving initial configuration\"}",
                "mariadb-1    | 2026-09-16 10:14:03 0 [Note] mariadbd: ready for connections.",
                "redis-1      | 1:M 16 Sep 2026 10:14:01.112 * Ready to accept connections tcp"
            }));
            Save(logs, dir, "window-logs");
        }

        static WizardForm InstallSample(float scale, bool details)
        {
            WizardForm w = Wizard(scale, false);
            w.page = WizardPage.Install;
            w.showDetails = details;
            foreach (string l in SampleLog) w.log.Append(l).Append("\r\n");
            w.OnInstallLine("##deployer:step 1/10 Checking this PC");
            w.OnInstallLine("##deployer:step 2/10 Getting Deployer files");
            w.OnInstallLine("##deployer:step 3/10 Setting up Docker Engine (WSL2)");
            w.OnInstallLine("##deployer:step 4/10 Writing configuration");
            w.OnInstallLine("##deployer:step 5/10 Downloading container images");
            w.progress = 0.46;
            w.transient = "mariadb  Downloading  [=================>        ]  61.2MB/88.4MB";
            w.Rebuild();
            return w;
        }

        static ControlForm ControlSample(float scale, int variant)
        {
            ControlForm c = new ControlForm(@"C:\ProgramData\Deployer", false, scale, true);
            c.port = 8080;
            StatusSnapshot s = new StatusSnapshot();
            s.Installed = true;
            s.Runtime = "wsl-engine";
            s.Version = "v0.1.0";
            s.Port = 8080;
            s.Engine = variant != 1;
            s.Autostart = true;
            foreach (string name in new[] { "api", "worker", "caddy", "dashboard", "mariadb", "mongodb", "redis", "tunnel" })
            {
                if (variant == 1) break;
                ServiceInfo i = new ServiceInfo();
                i.Name = name;
                i.State = "running";
                i.Health = name == "caddy" ? "" : (variant == 3 && name == "api" ? "unhealthy" : "healthy");
                s.Services.Add(i);
            }
            s.Taken = new DateTime(2026, 9, 16, 10, 24, 0);
            switch (variant)
            {
                case 0: c.ApplySample(s, true, null, "Backup finished at 10:21 (in the backups folder)", true); break;
                case 1: c.ApplySample(s, false, null, "Deployer stopped at 10:22. Your data is safe.", true); break;
                case 2: c.ApplySample(s, true, "Backing up", null, true); break;
                default: c.ApplySample(s, false, null, null, true); break;
            }
            return c;
        }

        /// <summary>Runs the embedded install.ps1 -DryRun through the real wizard install code path.</summary>
        static void LiveDryRun(string outDir)
        {
            WizardForm w = Wizard(1f, true);
            liveWizard = w;
            IntPtr handle = w.Handle;
            Stopwatch sw = Stopwatch.StartNew();
            w.StartInstall();
            while ((w.page == WizardPage.Install) && sw.Elapsed.TotalSeconds < 45)
            {
                Application.DoEvents();
                Thread.Sleep(30);
            }
            if (w.runner != null) w.runner.Cancel();
            Line("Live dry run finished in " + (int)sw.Elapsed.TotalSeconds + " s on page " + w.page + " (last step " + w.step + "/" + w.totalSteps + ")");
            File.WriteAllText(Path.Combine(outDir, "live-dryrun.log"), w.log.ToString());
            Check(w.page == WizardPage.Finish, "install.ps1 -DryRun completes and the wizard reaches the Finish page" +
                  (w.page == WizardPage.Error ? " (error: " + w.errorMessage + ")" : ""));
            Check(w.step == 10 && w.totalSteps == 10, "all 10 step markers were received");
            Check(w.log.ToString().Contains("[dry run] would"), "dry-run actions were streamed to the log");
            string dir = Path.Combine(outDir, "100");
            Directory.CreateDirectory(dir);
            Save(w, dir, "wizard-live-dryrun-result");
            GC.KeepAlive(handle);
        }
    }
}
