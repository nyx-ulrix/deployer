// Uninstall: confirm (optionally deleting all data), run "deployer uninstall", remove shortcuts and
// the Apps & Features entry. Runs from a temporary copy of the exe so the install folder can be removed.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace DeployerSetup
{
    class UninstallForm : ThemedForm
    {
        internal enum Phase { Confirm, Running, Done, Failed }

        internal Phase phase = Phase.Confirm;
        internal bool deleteData;
        readonly string installDir;
        readonly bool selfTest;
        readonly StringBuilder log = new StringBuilder();
        internal string transient = "";
        internal string failure = "";
        internal bool partial;  // setup stopped before runtime.json, so deployer.ps1 cannot uninstall it (A-078)
        internal bool leftover; // "delete everything" was chosen but the folder is still there
        internal bool foreign;  // partial, and the folder holds no setup files: nothing there is deleted or blamed
        ScriptRunner runner;
        string scriptRoot;
        TextBlock transientLabel;
        System.Windows.Forms.Timer anim;
        const int DesignWidth = 540;

        public UninstallForm(string installDir, float forcedScale, bool selfTest) : base(forcedScale)
        {
            this.installDir = installDir;
            this.selfTest = selfTest;
            Text = "Uninstall Deployer";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            BuildUi();
            if (!selfTest)
            {
                anim = new System.Windows.Forms.Timer();
                anim.Interval = 80;
                anim.Tick += delegate
                {
                    if (phase != Phase.Running) return;
                    foreach (Control c in Controls) if (c is IconBadge || c is ProgressLine) c.Invalidate();
                };
                anim.Start();
            }
        }

        internal void SetPhase(Phase p)
        {
            phase = p;
            Rebuild();
        }

        protected override void BuildUi()
        {
            int w = ui.S(DesignWidth);
            int pad = ui.S(28);
            int left = ui.S(96);
            int tw = w - left - pad;
            int y = pad;
            IconKind icon;
            Color color;
            string title, text;
            switch (phase)
            {
                case Phase.Running:
                    icon = IconKind.Spinner; color = Theme.Accent;
                    title = "Removing Deployer…";
                    text = "This takes a minute or two. Please keep this window open.";
                    break;
                case Phase.Done:
                    icon = IconKind.Check; color = Theme.Success;
                    title = "Deployer has been removed";
                    text = DoneText();
                    break;
                case Phase.Failed:
                    icon = IconKind.Cross; color = Theme.Danger;
                    title = "Uninstall didn't finish";
                    text = (string.IsNullOrEmpty(failure) ? "Something went wrong." : failure) + " You can try again, or copy the details when asking for help.";
                    break;
                default:
                    icon = IconKind.Warn; color = Theme.Danger;
                    title = "Uninstall Deployer?";
                    text = "This stops Deployer and removes its containers, the sign-in task, shortcuts and program files from this PC.";
                    break;
            }
            IconBadge badge = new IconBadge(ui, icon, color, icon != IconKind.Spinner);
            badge.Bounds = new Rectangle(pad, y, ui.S(48), ui.S(48));
            Controls.Add(badge);
            TextBlock t = new TextBlock(ui, title, ui.SemiBold(14f), Theme.Text);
            y += t.LayoutAt(left, y + ui.S(2), tw) + ui.S(10);
            Controls.Add(t);
            TextBlock m = new TextBlock(ui, text, ui.Font(10f), Theme.TextMuted);
            y += m.LayoutAt(left, y, tw);
            Controls.Add(m);

            if (phase == Phase.Confirm)
            {
                y += ui.S(20);
                Card card = new Card(ui, deleteData ? Theme.DangerSoft : Theme.SurfaceAlt, deleteData ? Glyphs.Blend(Theme.Danger, Color.White, 0.6f) : Theme.Border);
                CheckOption opt = new CheckOption(ui, "Also delete all databases and backups",
                    "Permanently deletes every project's data, your settings (.env) and the backups folder. This can't be undone.");
                opt.CheckColor = Theme.Danger;
                opt.Checked = deleteData;
                int cp = ui.S(16);
                opt.LayoutAt(cp, cp, tw - cp * 2);
                card.Bounds = new Rectangle(left, y, tw, opt.Height + cp * 2);
                opt.Changed += delegate { deleteData = opt.Checked; Rebuild(); };
                card.Controls.Add(opt);
                Controls.Add(card);
                y += card.Height;
                if (!deleteData)
                {
                    y += ui.S(10);
                    TextBlock keep = new TextBlock(ui, "Kept: databases, .env and backups in " + installDir, ui.Font(9f), Theme.TextSubtle);
                    y += keep.LayoutAt(left, y, tw);
                    Controls.Add(keep);
                }
            }
            else if (phase == Phase.Running)
            {
                y += ui.S(18);
                ProgressLine bar = new ProgressLine(ui);
                bar.Indeterminate = true;
                bar.Bounds = new Rectangle(left, y, tw, ui.S(6));
                Controls.Add(bar);
                y += ui.S(16);
                transientLabel = new TextBlock(ui, transient, ui.Font(9f), Theme.TextSubtle);
                transientLabel.SingleLine = true;
                transientLabel.LayoutAt(left, y, tw);
                Controls.Add(transientLabel);
                y += ui.Font(9f).Height;
            }
            y += pad;

            Panel footer = AddFooter(y, w);
            int fh = footer.Height;
            int right = w - pad;
            int bh = ui.S(38);
            List<FlatButton> buttons = new List<FlatButton>();
            switch (phase)
            {
                case Phase.Confirm:
                    buttons.Add(Button(deleteData ? "Delete everything" : "Uninstall", ButtonStyle.Danger, delegate { StartUninstall(); }));
                    buttons.Add(Button("Cancel", ButtonStyle.Secondary, delegate { Close(); }));
                    break;
                case Phase.Done:
                    buttons.Add(Button("Close", ButtonStyle.Primary, delegate { Close(); }));
                    break;
                case Phase.Failed:
                    buttons.Add(Button("Try again", ButtonStyle.Primary, delegate { SetPhase(Phase.Confirm); }));
                    FlatButton copy = Button("Copy details", ButtonStyle.Secondary, null);
                    copy.Click += delegate
                    {
                        try { Clipboard.SetText(failure + "\r\n\r\n" + log); copy.Text = "Copied"; } catch (Exception) { }
                    };
                    buttons.Add(copy);
                    buttons.Add(Button("Close", ButtonStyle.Ghost, delegate { Close(); }));
                    break;
                default:
                    FlatButton wait = Button("Please wait…", ButtonStyle.Secondary, null);
                    wait.Enabled = false;
                    buttons.Add(wait);
                    break;
            }
            foreach (FlatButton b in buttons)
            {
                int bw = b.PreferredWidth(ui.S(96));
                right -= bw;
                b.Bounds = new Rectangle(right, (fh - bh) / 2, bw, bh);
                right -= ui.S(10);
                footer.Controls.Add(b);
            }
            if (phase == Phase.Failed)
            {
                LinkText help = new LinkText(ui, "Troubleshooting help", AppInfo.TroubleshootingUrl);
                Size hs = help.Preferred();
                help.Bounds = new Rectangle(pad, (fh - hs.Height) / 2, hs.Width, hs.Height);
                footer.Controls.Add(help);
            }
            ClientSize = new Size(w, y + fh);
            if (buttons.Count > 0 && phase != Phase.Running) AcceptButton = buttons[0];
        }

        internal string DoneText()
        {
            if (partial && foreign)
                return "No Deployer setup files were found in " + installDir + ", so only the shortcuts and the Apps & Features entry were removed. Nothing in that folder was touched.";
            if (deleteData && leftover)
                return "Deployer was removed, but some of its files could not be deleted from " + installDir + ". Delete that folder yourself to free the space.";
            if (deleteData)
                return "Deployer and all of its data were removed from this PC.";
            if (partial)
                return "Setup never finished here, so only the shortcuts and the Apps & Features entry were removed. Its files are still in " + installDir +
                       ". To free the space, run \"wsl --unregister deployer\" if setup got that far, then delete that folder.";
            return "Your databases, settings (.env) and backups were kept in " + installDir + ". Install Deployer again to use them. To delete them instead, first run \"wsl --unregister deployer\" (if you used the free Docker Engine), then delete that folder.";
        }

        FlatButton Button(string text, ButtonStyle style, EventHandler click)
        {
            FlatButton b = new FlatButton(ui, text, style);
            if (click != null) b.Click += click;
            return b;
        }

        void StartUninstall()
        {
            if (selfTest) return;
            log.Length = 0;
            failure = "";
            transient = "Stopping Deployer";
            SetPhase(Phase.Running);
            try
            {
                Integration.StopOtherControlInstances();
                bool installed = File.Exists(Path.Combine(installDir, "runtime.json"));
                if (!installed)
                {
                    partial = true;
                    foreign = !IsSetupFolder(installDir);
                    bool wipe = deleteData;
                    System.Threading.Thread t = new System.Threading.Thread(() =>
                    {
                        string note = RemovePartialInstall(installDir, wipe, RunWsl);
                        Post(() => { log.Append(note); OnExited(0); });
                    });
                    t.IsBackground = true;
                    t.Start();
                    return;
                }
                scriptRoot = PrepareScripts();
                List<string> args = new List<string> { "uninstall", "-Yes", "-InstallDir", installDir };
                if (!deleteData) args.Add("-KeepData");
                runner = new ScriptRunner();
                runner.OutputLine += line => Post(() =>
                {
                    log.Append(line).Append("\r\n");
                    string t = ScriptOutput.Friendly(line);
                    if (t.Length > 0 && Marker.Parse(line) == null)
                    {
                        transient = t;
                        if (transientLabel != null) transientLabel.Text = t;
                    }
                });
                runner.Exited += code => Post(() => OnExited(code));
                runner.Start(Path.Combine(scriptRoot, "deployer.ps1"), args);
            }
            catch (Exception ex)
            {
                failure = ex.Message;
                log.Append(ex).Append("\r\n");
                SetPhase(Phase.Failed);
            }
        }

        /// <summary>
        /// Cleans up an install that stopped before install.ps1 wrote runtime.json, which "deployer uninstall"
        /// refuses to handle (A-078): unregisters the "deployer" WSL distro and deletes the folder. Only a folder
        /// setup itself created (it holds the Control exe or setup-options.json) is touched, so a wrong one is never wiped.
        /// </summary>
        internal static string RemovePartialInstall(string dir, bool deleteData, Func<string, ProcessResult> wsl)
        {
            StringBuilder note = new StringBuilder("runtime.json not found in " + dir + "; setup did not finish there.\r\n");
            if (!deleteData) return note.Append("Kept its files; removed shortcuts and the Apps & Features entry only.\r\n").ToString();
            if (!IsSetupFolder(dir))
                return note.Append("No Deployer setup files there; nothing was deleted.\r\n").ToString();
            ProcessResult list = wsl("--list --quiet");
            foreach (string line in list.StdOut.Split('\r', '\n'))
            {
                if (list.ExitCode != 0 || line.Trim().Trim('﻿') != DistroName) continue;
                ProcessResult r = wsl("--unregister " + DistroName);
                note.Append(r.ExitCode == 0 ? "WSL distro \"deployer\" removed.\r\n" : "wsl --unregister failed: " + r.StdOut + r.StdErr + "\r\n");
                break;
            }
            try
            {
                Directory.Delete(dir, true);
                note.Append("Deleted ").Append(dir).Append(".\r\n");
            }
            catch (Exception ex)
            {
                note.Append("Could not delete ").Append(dir).Append(": ").Append(ex.Message).Append("\r\n");
            }
            return note.ToString();
        }

        static bool IsSetupFolder(string dir)
        {
            return File.Exists(Integration.ControlExe(dir)) || File.Exists(Path.Combine(dir, AppInfo.OptionsFileName));
        }

        const string DistroName = "deployer"; // $script:DeployerDistro in installer/lib/common.ps1

        static ProcessResult RunWsl(string args)
        {
            return ProcessUtil.Run(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "wsl.exe"), args, 300000);
        }

        /// <summary>Copies the installed scripts to a temp folder (they are deleted during uninstall).</summary>
        string PrepareScripts()
        {
            string temp = Path.Combine(Path.GetTempPath(), "DeployerUninstall-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            string installed = Path.Combine(installDir, "installer");
            if (File.Exists(Path.Combine(installed, "deployer.ps1")) && File.Exists(Path.Combine(installed, @"lib\common.ps1")))
            {
                CopyTree(installed, temp);
                return temp;
            }
            string root = Payload.Extract();
            return Path.Combine(root, "installer");
        }

        static void CopyTree(string from, string to)
        {
            Directory.CreateDirectory(to);
            foreach (string f in Directory.GetFiles(from)) File.Copy(f, Path.Combine(to, Path.GetFileName(f)), true);
            foreach (string d in Directory.GetDirectories(from)) CopyTree(d, Path.Combine(to, Path.GetFileName(d)));
        }

        void OnExited(int code)
        {
            runner = null;
            if (code != 0)
            {
                failure = ScriptOutput.LastError(log) ?? "The uninstall script stopped (exit code " + code + ").";
                SetPhase(Phase.Failed);
                return;
            }
            Integration.RemoveShortcuts();
            Integration.RemoveUninstallEntry();
            Integration.ClearResume();
            try
            {
                string exe = Integration.ControlExe(installDir);
                if (File.Exists(exe)) File.Delete(exe);
                string opts = Path.Combine(installDir, AppInfo.OptionsFileName);
                if (File.Exists(opts)) File.Delete(opts);
                if (deleteData && Directory.Exists(installDir) && Directory.GetFileSystemEntries(installDir).Length == 0) Directory.Delete(installDir);
            }
            catch (Exception)
            {
            }
            leftover = deleteData && Directory.Exists(installDir);
            SetPhase(Phase.Done);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (phase == Phase.Running && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                return;
            }
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            if (anim != null) anim.Stop();
            if (scriptRoot != null)
            {
                try
                {
                    string dir = scriptRoot.EndsWith("installer") ? Path.GetDirectoryName(scriptRoot) : scriptRoot;
                    if (dir != null && dir.StartsWith(Path.GetTempPath(), StringComparison.OrdinalIgnoreCase)) Directory.Delete(dir, true);
                }
                catch (Exception)
                {
                }
            }
            base.OnFormClosed(e);
        }
    }
}
