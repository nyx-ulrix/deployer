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
            m = Marker.Parse("##deployer:done url=http://localhost:8080 lan=http://192.168.1.20:8080,http://10.0.0.5:8080 publicnet=1");
            Check(m.Values["lan"] == "http://192.168.1.20:8080,http://10.0.0.5:8080" && m.Values["publicnet"] == "1", "done marker carries the LAN addresses and Public networks");
            StatusSnapshot lan = StatusSnapshot.FromJson("{\"installed\":true,\"lan\":true,\"lanUrls\":[\"http://192.168.1.20:8080\"],\"publicNetworks\":[]}");
            Check(lan.LanLine() == "On other devices open http://192.168.1.20:8080", "Control shows the LAN address");
            lan = StatusSnapshot.FromJson("{\"installed\":true,\"lan\":true,\"lanUrls\":[\"http://192.168.1.20:8080\"],\"publicNetworks\":[\"CafeWifi\"]}");
            Check(lan.LanLine().Contains("\"CafeWifi\" as Public"), "Control warns about a Public network");
            Check(StatusSnapshot.FromJson("{\"installed\":true,\"lan\":false}").LanLine() == null, "no LAN line with LAN access off");
            m = Marker.Parse("##deployer:check port fail Port 8080 is already used by: nginx.");
            Check(m != null && m.Kind == MarkerKind.Check && m.CheckId == "port" && m.CheckState == "fail", "check marker parses");
            Check(Ports.IsAppPort(8150) && !Ports.IsAppPort(8090) && !Ports.IsAppPort(Ports.SuggestFree(8150)), "app port range is never the dashboard port");
            Check(Marker.Parse("##deployer:reboot-required").Kind == MarkerKind.RebootRequired, "reboot marker parses");
            Check(Marker.Parse("##deployer:error Something broke").Text == "Something broke", "error marker parses");
            Check(Marker.Parse("    [ok] not a marker") == null, "plain output is not a marker");
            Check(ProcessUtil.Quote(@"C:\Program Files\Deployer\") == "\"C:\\Program Files\\Deployer\\\\\"", "argument quoting doubles trailing backslashes");
            string gid = "1234-abc.apps.googleusercontent.com";
            Check(SignInAppsDialog.CheckValue("google", false, gid) == null
                  && SignInAppsDialog.CheckValue("google", false, "ID " + gid + " SECRET x") != null
                  && SignInAppsDialog.CheckValue("github", false, "ID Ov23liExample") != null
                  && SignInAppsDialog.CheckValue("google", true, gid) != null
                  && SignInAppsDialog.CheckValue("github", true, "secret:abc") != null, "sign-in app paste checks");
            Dictionary<string, object> local = SampleOAuthStatus();
            ((Dictionary<string, object>)local["google"])["callback_url"] = "http://localhost:8090/v1/auth/oauth/google/callback";
            ((Dictionary<string, object>)local["github"])["callback_url"] = "http://localhost:8090/v1/auth/oauth/github/callback";
            string callbacks = SignInAppsDialog.CallbackChangeNote(local, 8090);
            Dictionary<string, object> noApps = SampleOAuthStatus();
            ((Dictionary<string, object>)noApps["google"])["client_id"] = "";
            Check(callbacks != null && callbacks.Contains("Google: http://localhost:8090/v1/auth/oauth/google/callback") && !callbacks.Contains("GitHub:")
                  && SignInAppsDialog.CallbackChangeNote(noApps, 8090) == null && SignInAppsDialog.CallbackChangeNote(null, 8090) == null
                  && SignInAppsDialog.CallbackChangeNote(SampleOAuthStatus(), 8090) == null,
                  "a port change names the new callback URLs only for set-up sign-in apps whose address carries the port (A-155)");
            Check(ResetPasswordDialog.Check("short", "short") != null
                  && ResetPasswordDialog.Check("long-enough-1", "long-enough-2") != null
                  && ResetPasswordDialog.Check("long-enough-1", "long-enough-1") == null, "reset password checks");
            Check(SystemChecks.MemoryCheck(4).Title.Contains("about 2 GB is available to Deployer; expect 1-2 small apps")
                  && SystemChecks.MemoryCheck(3).Detail.Contains("exit code 137"), "memory check says how much WSL gives Deployer (A-070)");
            CheckResult fullC = SystemChecks.DiskCheck("C:", 2, "D:", 50), stuck = SystemChecks.DiskCheck("C:", 2, null, 0);
            Check(!fullC.Blocking && fullC.Detail.Contains("D:") && fullC.Detail.Contains("Options page")
                  && stuck.Blocking && !stuck.Detail.Contains("Options page") && SystemChecks.DiskCheck("C:", 2, "D:", 5).Blocking
                  && SystemChecks.DirSpaceError("C", 2) != null && SystemChecks.DirSpaceError("D", 50) == null,
                  "a full drive warns and names a roomier one, and the Options page enforces 4 GB on the chosen folder (A-154)");
            string other = SystemChecks.OtherAccountWarning(@"PC\Admin", @"PC\Kid");
            Check(other != null && other.Contains("installed for Admin") && other.Contains("tray icon won't appear for Kid")
                  && SystemChecks.OtherAccountWarning(@"PC\kid", @"PC\Kid") == null
                  && SystemChecks.OtherAccountWarning(@"PC\Kid", "Kid") == null
                  && SystemChecks.OtherAccountWarning(@"PC\Admin", null) == null,
                  "setup warns when UAC ran it as another account (A-079)");
            using (ControlForm running = ControlSample(1f, 0), stopped = ControlSample(1f, 1), broken = ControlSample(1f, 3))
                Check(running.updateButton.Enabled && !stopped.updateButton.Enabled && broken.updateButton.Enabled,
                      "Update needs the database running, not a healthy API (A-076)");
            using (ControlForm checking = ControlSample(1f, 5), failed = ControlSample(1f, 4))
                Check(checking.State == RunState.Checking && failed.State == RunState.NotResponding && !failed.updateButton.Enabled,
                      "a failed status run shows advice instead of Checking forever (A-099)");
            using (ControlForm stopped = ControlSample(1f, 1))
            using (WizardForm done = Wizard(1f, false))
            {
                done.page = WizardPage.Options;
                done.Rebuild();
                TextBlock ht = stopped.heroText;
                Check(ht.Text.Contains("signed in to Windows") && ht.Height >= 2 * ht.TextFont.Height && ht.Bottom <= ht.Parent.ClientSize.Height
                      && AllText(done).Contains(WizardForm.SignedInNote),
                      "Control's Stopped text and the Options page say signing out or a restart stops Deployer (A-100)");
            }
            Check(AppInfo.CompareVersions("0.10.0", "0.9.9") > 0 && AppInfo.CompareVersions("v0.3.0", "0.3.0") == 0
                  && AppInfo.CompareVersions("0.3.0", "0.3.0-rc.1") > 0 && AppInfo.CompareVersions("main", "0.0.1") < 0
                  && InstallLocator.IsUpdate("0.4.0", "0.3.0", "0.3.0") && InstallLocator.IsUpdate("0.4.0", null, null)
                  && !InstallLocator.IsUpdate("0.3.0", "0.3.0", "0.3.0") && !InstallLocator.IsUpdate("0.4.0", "0.3.0", "0.5.0")
                  && InstallLocator.IsUpdate("0.5.0", "0.3.0", "0.5.0"), "a newer exe offers to update, never to downgrade (A-074)");
            Check(InstallLocator.NewerThan("0.3.0", "0.5.0") == "0.5.0" && InstallLocator.NewerThan("0.5.0", "0.5.0") == null
                  && InstallLocator.NewerThan("0.5.0", null) == null && InstallLocator.NewerThan("0.5.0", "0.5.0-rc.1") == null,
                  "setup from an older exe does not downgrade what 'deployer update' installed (A-074)");

            using (WizardForm up = UpdateOptionsSample(1f))
                Check(up.portInput.Box.ReadOnly && CountToggles(up) == 1,
                      "an update locks the port and leaves only the shortcut toggle; the rest is in Control Settings (A-077)");
            using (WizardForm up = UpdateOptionsSample(1f))
            {
                up.installedPort = up.options.Port = 8150;
                up.Rebuild();
                Check(!up.portInput.Box.ReadOnly, "an update from an app-range port (before A-064) can still move the port (A-077)");
            }

            using (WizardForm up = Wizard(1f, false))
            {
                up.installedDir = @"C:\ProgramData\Deployer";
                up.page = WizardPage.Docker;
                up.Rebuild();
                string note = AllText(up);
                Check(note.Contains("Export & import") && note.Contains("Restore from export") && !note.Contains("keeping your data"),
                      "the runtime note says to export and restore when switching, not to keep the data (A-095)");
            }

            using (WizardForm fresh = Wizard(1f, false), up = Wizard(1f, false), repair = Wizard(1f, false))
            {
                fresh.page = up.page = repair.page = WizardPage.Finish;
                fresh.doneUrl = up.doneUrl = repair.doneUrl = "http://localhost:8080";
                up.installedDir = repair.installedDir = @"C:\ProgramData\Deployer";
                up.updating = up.newVersion = repair.updating = true;
                fresh.Rebuild();
                up.Rebuild();
                repair.Rebuild();
                string freshText = AllText(fresh), upText = AllText(up), repairText = AllText(repair);
                Check(freshText.Contains("Create your owner account") && fresh.finishOpenUrl == "http://localhost:8080/setup"
                      && upText.Contains("updated to " + AppInfo.Version) && upText.Contains("were kept")
                      && !upText.Contains("owner account") && up.finishOpenUrl == "http://localhost:8080/"
                      && !repairText.Contains("updated to") && repairText.Contains(AppInfo.Version + " is ready") && repair.finishOpenUrl == "http://localhost:8080/",
                      "the Finish page after an update says so, a same-version repair does not claim one, and both open the dashboard, not the first-run setup (A-156)");
            }

            string half = Path.Combine(Path.GetTempPath(), "DeployerSelfTest-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(half);
            try
            {
                File.WriteAllText(Path.Combine(half, AppInfo.OptionsFileName), "{}");
                File.WriteAllText(Path.Combine(half, "runtime.json"), "{}");
                bool unfinished = !InstallLocator.IsFinished(half);
                File.Delete(Path.Combine(half, AppInfo.OptionsFileName));
                Check(unfinished && InstallLocator.IsFinished(half) && !InstallLocator.IsFinished(null),
                      "a half-finished install reopens the wizard, not Control (A-073)");
            }
            finally
            {
                Directory.Delete(half, true);
            }

            Directory.CreateDirectory(Path.Combine(half, "wsl"));
            try
            {
                List<string> wslCalls = new List<string>();
                Func<string, ProcessResult> fakeWsl = a =>
                {
                    wslCalls.Add(a);
                    ProcessResult r = new ProcessResult();
                    r.ExitCode = 0;
                    r.StdOut = "Ubuntu\r\ndeployer\r\n";
                    return r;
                };
                UninstallForm.RemovePartialInstall(half, true, fakeWsl);
                bool strangerKept = Directory.Exists(half) && wslCalls.Count == 0;
                File.WriteAllText(Path.Combine(half, AppInfo.OptionsFileName), "{}");
                UninstallForm.RemovePartialInstall(half, false, fakeWsl);
                bool keptWhenAsked = Directory.Exists(half) && wslCalls.Count == 0;
                UninstallForm.RemovePartialInstall(half, true, fakeWsl);
                Check(strangerKept && keptWhenAsked && !Directory.Exists(half) && wslCalls.Contains("--unregister deployer"),
                      "uninstalling a half-install with delete ticked removes its WSL distro and folder, never a folder setup didn't make (A-078)");
            }
            finally
            {
                if (Directory.Exists(half)) Directory.Delete(half, true);
            }
            using (UninstallForm u = new UninstallForm(half, 1f, true))
            {
                u.partial = true;
                bool honestKeep = u.DoneText().Contains("never finished") && u.DoneText().Contains(half);
                u.deleteData = true;
                u.leftover = true;
                Check(honestKeep && u.DoneText().Contains("could not be deleted"), "the uninstaller never claims data it left behind was removed (A-078)");
                u.foreign = true;
                Check(u.DoneText().Contains("Nothing in that folder") && !u.DoneText().Contains("Delete that folder"),
                      "the uninstaller never tells you to delete a folder setup didn't make (A-078)");
            }
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
                // Windows clamps a top-level window to the virtual screen. On small displays (CI runners at
                // 1024x768, DPI-unaware sessions) the forced 150 % render is clamped while its children keep
                // their design size, so the overflow check would report bogus failures. Real runs shrink to
                // fit the screen instead (see WizardForm), which is not what the forced scale exercises.
                Size maxTrack = SystemInformation.MaxWindowTrackSize;
                bool clamped = form.Width >= maxTrack.Width || form.Height >= maxTrack.Height;
                if (clamped)
                    Line("SKIP  " + Path.GetFileName(dir) + "/" + name + " layout: window clamped to the screen (" + form.Size + " vs max " + maxTrack + ")");
                else
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
            w.updating = w.newVersion = false;
            w.options = new SetupOptions();
            w.options.Port = Ports.IsFree(8080) ? 8080 : Ports.SuggestFree(8080);
            return w;
        }

        static WizardForm UpdateOptionsSample(float scale)
        {
            WizardForm w = Wizard(scale, false);
            w.installedDir = @"C:\ProgramData\Deployer";
            w.installedPort = w.options.Port;
            w.page = WizardPage.Options;
            w.Rebuild();
            return w;
        }

        static string AllText(Control c)
        {
            StringBuilder sb = new StringBuilder(c.Text).Append('\n');
            ToggleRow toggle = c as ToggleRow;
            if (toggle != null) sb.Append(toggle.Description).Append('\n');
            foreach (Control child in c.Controls) sb.Append(AllText(child));
            return sb.ToString();
        }

        static int CountToggles(Control c)
        {
            int n = c is ToggleRow ? 1 : 0;
            foreach (Control child in c.Controls) n += CountToggles(child);
            return n;
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
                r.Items.Add(SystemChecks.MemoryCheck(3.5));
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
            w.installedDir = @"C:\ProgramData\Deployer";
            w.otherAccount = SystemChecks.OtherAccountWarning(@"PC\Administrator", @"PC\Student");
            w.Rebuild();
            Save(w, dir, "wizard-1-welcome-other-account");

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
            w.ApplyReport(SampleReport(1));
            w.installedDir = @"C:\ProgramData\Deployer";
            w.page = WizardPage.Docker;
            w.Rebuild();
            Save(w, dir, "wizard-3-docker-update");

            w = Wizard(scale, false);
            w.ApplyReport(SampleReport(0));
            w.options.Port = Ports.IsFree(8080) ? 8080 : Ports.SuggestFree(8080);
            w.page = WizardPage.Options;
            w.Rebuild();
            Save(w, dir, "wizard-4-options");
            Save(UpdateOptionsSample(scale), dir, "wizard-4-options-update");

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

            w = Wizard(scale, false);
            w.page = WizardPage.Finish;
            w.doneUrl = "http://localhost:8080";
            w.doneLan = "http://192.168.1.20:8080";
            w.Rebuild();
            Save(w, dir, "wizard-6-finish-lan");

            w = Wizard(scale, false);
            w.installedDir = @"C:\ProgramData\Deployer";
            w.updating = w.newVersion = true;
            w.page = WizardPage.Finish;
            w.doneUrl = "http://localhost:8080";
            w.Rebuild();
            Save(w, dir, "wizard-6-finish-update");

            w = Wizard(scale, false);
            w.page = WizardPage.Finish;
            w.doneUrl = "http://localhost:8080";
            w.doneLan = "http://192.168.1.20:8080";
            w.donePublicNetworks = 1;
            w.Rebuild();
            Save(w, dir, "wizard-6-finish-public");

            w = Wizard(scale, true);
            w.page = WizardPage.Welcome;
            w.Rebuild();
            Save(w, dir, "wizard-testmode-welcome");

            // Deployer Control
            Save(ControlSample(scale, 0), dir, "control-running");
            Save(ControlSample(scale, 1), dir, "control-stopped");
            Save(ControlSample(scale, 2), dir, "control-busy");
            Save(ControlSample(scale, 3), dir, "control-not-responding");
            Save(ControlSample(scale, 4), dir, "control-status-failed");

            Save(new SettingsDialog(8080, false, true, true, scale, null, null), dir, "dialog-settings");
            Save(new SettingsDialog(8080, true, true, true, scale, new List<string> { "http://192.168.1.20:8080" }, null), dir, "dialog-settings-lan");
            Save(new SettingsDialog(8080, true, true, true, scale, null, new List<string> { "CafeWifi" }), dir, "dialog-settings-public");
            Save(new SignInAppsDialog(null, @"C:\ProgramData\Deployer", scale), dir, "dialog-signin-empty");
            SignInAppsDialog signIn = new SignInAppsDialog(null, @"C:\ProgramData\Deployer", scale);
            signIn.ApplyStatus(SampleOAuthStatus(), null);
            Save(signIn, dir, "dialog-signin-google");
            signIn = new SignInAppsDialog(null, @"C:\ProgramData\Deployer", scale);
            signIn.provider = "github";
            signIn.message = SignInAppsDialog.CheckValue("github", false, "ID Ov23liExample SECRET abc");
            signIn.messageIsError = true;
            signIn.ApplyStatus(SampleOAuthStatus(), null);
            Save(signIn, dir, "dialog-signin-github-error");
            ResetPasswordDialog resetPassword = new ResetPasswordDialog(null, @"C:\ProgramData\Deployer", scale);
            resetPassword.message = ResetPasswordDialog.Check("new-password-1", "new-password-2");
            resetPassword.messageIsError = true;
            resetPassword.Rebuild();
            Save(resetPassword, dir, "dialog-reset-password");
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

        static Dictionary<string, object> SampleOAuthStatus()
        {
            Dictionary<string, object> google = new Dictionary<string, object>();
            google["client_id"] = "1234567890-abc123def456.apps.googleusercontent.com";
            google["has_secret"] = true;
            google["configured"] = true;
            google["callback_url"] = "https://deployer.example.org/v1/auth/oauth/google/callback";
            Dictionary<string, object> github = new Dictionary<string, object>();
            github["client_id"] = null;
            github["has_secret"] = false;
            github["configured"] = false;
            github["callback_url"] = "https://deployer.example.org/v1/auth/oauth/github/callback";
            Dictionary<string, object> s = new Dictionary<string, object>();
            s["public_url"] = "https://deployer.example.org";
            s["google"] = google;
            s["github"] = github;
            return s;
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
                case 4: c.statusFailed = true; c.ApplySample(null, false, null, null, true); break;
                case 5: c.ApplySample(null, false, null, null, true); break;
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
