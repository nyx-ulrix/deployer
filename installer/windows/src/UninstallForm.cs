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
                    text = deleteData
                        ? "Deployer and all of its data were removed from this PC."
                        : "Your databases, settings (.env) and backups were kept in " + installDir + ". Install Deployer again to use them, or delete that folder yourself.";
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

            Panel footer = new Panel();
            footer.BackColor = Theme.SurfaceAlt;
            int fh = ui.S(68);
            footer.Bounds = new Rectangle(0, y, w, fh);
            Rule fr = new Rule(Theme.Border);
            fr.Bounds = new Rectangle(0, 0, w, Math.Max(1, ui.S(1)));
            footer.Controls.Add(fr);
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
            Controls.Add(footer);
            ClientSize = new Size(w, y + fh);
            if (buttons.Count > 0 && phase != Phase.Running) AcceptButton = buttons[0];
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
                    log.Append("runtime.json not found in ").Append(installDir).Append("; removing shortcuts and the Apps & Features entry only.\r\n");
                    OnExited(0);
                    return;
                }
                scriptRoot = PrepareScripts();
                List<string> args = new List<string> { "uninstall", "-Yes", "-InstallDir", installDir };
                if (!deleteData) args.Add("-KeepData");
                runner = new ScriptRunner();
                runner.OutputLine += line => Post(() =>
                {
                    log.Append(line).Append("\r\n");
                    string t = line.Trim();
                    if (t.Length > 0 && Marker.Parse(t) == null)
                    {
                        if (t.StartsWith("==> ")) t = t.Substring(4);
                        if (t.StartsWith("[ok] ") || t.StartsWith("[!] ") || t.StartsWith("[x] ")) t = t.Substring(t.IndexOf(']') + 2);
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

        void Post(Action a)
        {
            try
            {
                if (!IsDisposed) BeginInvoke(a);
            }
            catch (InvalidOperationException)
            {
            }
        }

        void OnExited(int code)
        {
            runner = null;
            if (code != 0)
            {
                failure = "The uninstall script stopped (exit code " + code + ").";
                string[] lines = log.ToString().Split(new[] { "\r\n" }, StringSplitOptions.None);
                for (int i = lines.Length - 1; i >= 0; i--)
                {
                    if (lines[i].Trim().StartsWith("[x] "))
                    {
                        failure = lines[i].Trim().Substring(4);
                        break;
                    }
                }
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
