// DeployerSetup.exe entry point.
//
//   (no arguments)       Setup wizard, or Deployer Control when Deployer is already installed
//   /setup               Setup wizard (also updates an existing installation)
//   /dryrun              Setup wizard in test mode: install.ps1 -DryRun, nothing is changed
//   /resume              Continue an installation after the restart (registered in RunOnce)
//   /control             Deployer Control window
//   /tray                Deployer Control in the notification area (started at sign-in)
//   /uninstall [dir]     Uninstall (runs from a temporary copy)
//   /selftest <outdir>   Render every page to PNG files and run a live dry run, then exit
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("Deployer Setup")]
[assembly: AssemblyProduct("Deployer")]
[assembly: AssemblyCompany("Deployer contributors")]
[assembly: AssemblyCopyright("MIT License (c) 2026 Deployer contributors")]

namespace DeployerSetup
{
    static class Program
    {
        public static bool SelfTestMode;

        [STAThread]
        static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (s, e) => Crash(e.Exception);
            AppDomain.CurrentDomain.UnhandledException += (s, e) => Crash(e.ExceptionObject as Exception);

            try
            {
                if (Has(args, "/selftest"))
                {
                    SelfTestMode = true;
                    string outDir = After(args, "/selftest") ?? Path.Combine(Environment.CurrentDirectory, "selftest");
                    return SelfTest.Run(Path.GetFullPath(outDir));
                }
                if (Has(args, "/uninstall")) return RunUninstall(After(args, "/uninstall"));
                if (Has(args, "/tray")) return RunControl(true);
                if (Has(args, "/control")) return RunControl(false);
                if (Has(args, "/resume")) return RunWizard(false, true);
                if (Has(args, "/dryrun")) return RunWizard(true, false);
                if (Has(args, "/setup")) return RunWizard(false, false);
                if (Has(args, "/?") || Has(args, "/help") || Has(args, "-h") || Has(args, "--help"))
                {
                    MessageDialog.Info(null, "Deployer Setup " + AppInfo.Version,
                        "DeployerSetup.exe [/setup | /dryrun | /control | /tray | /uninstall | /selftest <folder>]\n\n" +
                        "Without options it opens the setup wizard, or Deployer Control if Deployer is already installed.");
                    return 0;
                }
                return InstallLocator.Find() != null ? RunControl(false) : RunWizard(false, false);
            }
            catch (Exception ex)
            {
                Crash(ex);
                return 1;
            }
        }

        static bool Has(string[] args, string name)
        {
            return args.Any(a => string.Equals(a, name, StringComparison.OrdinalIgnoreCase) ||
                                 string.Equals(a, "-" + name.TrimStart('/'), StringComparison.OrdinalIgnoreCase));
        }

        static string After(string[] args, string name)
        {
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase) && !args[i + 1].StartsWith("/")) return args[i + 1];
            }
            return null;
        }

        static void Crash(Exception ex)
        {
            if (ex == null) return;
            if (SelfTestMode)
            {
                Console.Error.WriteLine(ex);
                Environment.Exit(1);
            }
            try
            {
                ErrorDialog.Show(null, "Something went wrong",
                    "Deployer Setup ran into an unexpected problem. Nothing is lost — you can close this window and start it again.",
                    ex.ToString());
            }
            catch (Exception)
            {
                MessageBox.Show(ex.Message, "Deployer Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        static int RunWizard(bool dryRun, bool resume)
        {
            bool created;
            using (Mutex mutex = new Mutex(true, @"Local\DeployerSetupWizard", out created))
            {
                if (!created)
                {
                    MessageDialog.Info(null, "Setup is already running", "Deployer Setup is already open. Look for its window on the taskbar.");
                    return 0;
                }
                Application.Run(new WizardForm(dryRun, resume, 0, false));
                GC.KeepAlive(mutex);
            }
            return 0;
        }

        static int RunControl(bool trayMode)
        {
            string dir = InstallLocator.Find();
            if (dir == null)
            {
                if (trayMode) return 0;
                DialogResult r = MessageDialog.Ask(null, "Deployer isn't installed yet",
                    "Deployer Control manages an installed Deployer. Would you like to install Deployer now?",
                    IconKind.Info, Theme.Accent, "Install Deployer", ButtonStyle.Primary, "Close");
                return r == DialogResult.Yes ? RunWizard(false, false) : 0;
            }
            bool created;
            using (Mutex mutex = new Mutex(true, @"Local\DeployerControl", out created))
            using (EventWaitHandle showSignal = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\DeployerControl.Show"))
            {
                if (!created)
                {
                    // Another copy (usually the tray icon) is running: ask it to show its window.
                    if (!trayMode) showSignal.Set();
                    return 0;
                }
                ControlForm form = new ControlForm(dir, trayMode, 0, false);
                Thread listener = new Thread(() =>
                {
                    while (true)
                    {
                        showSignal.WaitOne();
                        try
                        {
                            form.BeginInvoke((Action)form.ShowWindow);
                        }
                        catch (Exception)
                        {
                            return;
                        }
                    }
                });
                listener.IsBackground = true;
                listener.Start();
                Application.Run(form);
                GC.KeepAlive(mutex);
            }
            return 0;
        }

        static int RunUninstall(string dirArg)
        {
            string dir = dirArg;
            if (string.IsNullOrEmpty(dir)) dir = InstallLocator.Find() ?? InstallLocator.RegisteredInstallDir();
            if (string.IsNullOrEmpty(dir)) dir = Path.GetDirectoryName(AppInfo.ExePath);
            dir = dir.TrimEnd('\\');

            bool fromTemp = AppInfo.ExePath.StartsWith(Path.GetTempPath(), StringComparison.OrdinalIgnoreCase);
            if (!fromTemp)
            {
                LaunchUninstaller(dir);
                return 0;
            }
            UninstallForm form = new UninstallForm(dir, 0, false);
            form.PlaceCentered(null);
            Application.Run(form);
            Integration.DeleteAfterExit(AppInfo.ExePath);
            return 0;
        }

        /// <summary>Copies this exe to %TEMP% and starts the uninstaller from there, so the install folder can be deleted.</summary>
        public static void LaunchUninstaller(string installDir)
        {
            string temp = Path.Combine(Path.GetTempPath(), "DeployerUninstall-" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".exe");
            File.Copy(AppInfo.ExePath, temp, true);
            ProcessStartInfo psi = new ProcessStartInfo(temp, "/uninstall " + ProcessUtil.Quote(installDir));
            psi.UseShellExecute = false;
            psi.WorkingDirectory = Path.GetTempPath();
            Process.Start(psi);
        }
    }
}
