// Deployer Control: status, start/stop/restart, update, backup, logs, settings, uninstall, tray icon.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace DeployerSetup
{
    class ServiceInfo
    {
        public string Name = "";
        public string State = "";
        public string Health = "";
    }

    class StatusSnapshot
    {
        public bool Installed;
        public string Runtime = "";
        public string Version = "";
        public int Port = 8080;
        public bool Engine;
        public bool Healthy;
        public bool Autostart;
        public bool Lan;
        public bool KeepAwake;
        public bool ManagedMongodb = true;
        public readonly List<ServiceInfo> Services = new List<ServiceInfo>();
        public DateTime Taken = DateTime.Now;

        public static StatusSnapshot FromJson(string json)
        {
            IDictionary<string, object> d = Json.Parse(json) as IDictionary<string, object>;
            if (d == null) return null;
            StatusSnapshot s = new StatusSnapshot();
            s.Installed = Json.Bool(d, "installed");
            s.Runtime = Json.Str(d, "runtime");
            s.Version = Json.Str(d, "version");
            s.Port = Json.Int(d, "port", 8080);
            s.Engine = Json.Bool(d, "engine");
            s.Healthy = Json.Bool(d, "healthy");
            s.Autostart = Json.Bool(d, "autostart");
            s.Lan = Json.Bool(d, "lan");
            s.KeepAwake = Json.Bool(d, "keepAwake");
            s.ManagedMongodb = !d.ContainsKey("managedMongodb") || Json.Bool(d, "managedMongodb");
            foreach (IDictionary<string, object> svc in Json.List(d, "services"))
            {
                ServiceInfo i = new ServiceInfo();
                i.Name = Json.Str(svc, "name");
                i.State = Json.Str(svc, "state");
                i.Health = Json.Str(svc, "health");
                s.Services.Add(i);
            }
            return s;
        }

        public static string RuntimeLabel(string runtime)
        {
            switch (runtime)
            {
                case "wsl-engine": return "Free Docker Engine (WSL2)";
                case "docker-desktop": return "Docker Desktop";
                case "existing": return "Your existing Docker";
                default: return runtime;
            }
        }
    }

    enum RunState { Checking, Running, Starting, NotResponding, Stopped, Busy }

    class ServiceTile : PaintedControl
    {
        public string Title = "";
        public string StateText = "";
        public Color Dot = Theme.Neutral;

        public ServiceTile(Ui ui) : base(ui)
        {
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f);
            using (GraphicsPath p = Logo.RoundedRect(r, ui.S(9)))
            {
                using (SolidBrush b = new SolidBrush(Theme.Surface)) g.FillPath(b, p);
                using (Pen pen = new Pen(Theme.Border, Math.Max(1f, ui.Factor))) g.DrawPath(pen, p);
            }
            float dot = ui.S(10);
            Font tf = ui.SemiBold(10f);
            Font sf = ui.Font(9f);
            int block = tf.Height + sf.Height;
            int top = (Height - block) / 2;
            using (SolidBrush b = new SolidBrush(Dot))
                g.FillEllipse(b, ui.S(14), top + (tf.Height - dot) / 2f, dot, dot);
            int tx = ui.S(36);
            TextRenderer.DrawText(g, Title, tf, new Rectangle(tx, top, Width - tx - ui.S(8), tf.Height), Theme.Text,
                TextFormatFlags.NoPadding | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
            TextRenderer.DrawText(g, StateText, sf, new Rectangle(tx, top + tf.Height, Width - tx - ui.S(8), sf.Height + ui.S(2)), Theme.TextSubtle,
                TextFormatFlags.NoPadding | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
        }
    }

    class StatusPill : PaintedControl
    {
        public string Label = "";
        public Color Color = Theme.Neutral;

        public StatusPill(Ui ui) : base(ui)
        {
            BackColor = Color.Transparent;
        }

        public int PreferredWidth()
        {
            return Ui.MeasureWidth(Label, ui.SemiBold(9.5f)) + ui.S(40);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(0, 0, Width - 1, Height - 1);
            using (GraphicsPath p = Logo.RoundedRect(r, r.Height / 2f))
            using (SolidBrush b = new SolidBrush(Glyphs.Blend(Color, Color.White, 0.86f)))
                g.FillPath(b, p);
            float dot = ui.S(8);
            using (SolidBrush b = new SolidBrush(Color))
                g.FillEllipse(b, ui.S(14), (Height - dot) / 2f, dot, dot);
            TextRenderer.DrawText(g, Label, ui.SemiBold(9.5f), new Rectangle(ui.S(28), 0, Width - ui.S(34), Height), Glyphs.Blend(Color, Color.Black, 0.35f),
                TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding | TextFormatFlags.SingleLine);
        }
    }

    class ControlForm : ThemedForm
    {
        const int DesignWidth = 780;
        const int DesignHeight = 608;

        internal readonly string installDir;
        internal int port;
        internal StatusSnapshot status;
        internal bool healthy;
        bool healthKnown;
        bool everHealthy;
        int failedPolls;
        DateTime lastUserAction = DateTime.MinValue;
        DateTime lastStartRequest = DateTime.MinValue;
        internal string actionName;
        internal string actionVerb = "";
        internal readonly StringBuilder actionLog = new StringBuilder();
        internal string lastResult = "";
        internal bool lastResultOk = true;
        internal string transient = "";
        ScriptRunner runner;
        readonly Queue<string[]> pending = new Queue<string[]>();
        string extractedRoot;
        readonly bool trayMode;
        readonly bool selfTest;
        NotifyIcon tray;
        ContextMenuStrip trayMenu;
        ToolStripMenuItem trayStatusItem;
        System.Windows.Forms.Timer healthTimer, statusTimer, animTimer;
        bool healthBusy, statusBusy;
        bool exiting;
        bool shownTrayHint;
        OutputWindow outputWindow;

        StatusPill pill;
        TextBlock heroTitle, heroText, activityText, updatedText;
        IconBadge heroIcon;
        Card hero;
        IconBadge activityIcon;
        FlatButton startButton, stopButton, restartButton, updateButton, backupButton, settingsButton, uninstallButton, openButton, deviceButton;
        bool deviceBusy;
        readonly Dictionary<string, ServiceTile> tiles = new Dictionary<string, ServiceTile>();

        // Every compose service (deploy/docker-compose.yml). "tunnel" idles until remote access is enabled,
        // so a stopped tunnel container is shown as "Off", not as a problem.
        static readonly string[] ServiceOrder = { "caddy", "api", "dashboard", "worker", "mariadb", "mongodb", "redis", "tunnel" };
        const int ServiceColumns = 4;

        public ControlForm(string installDir, bool trayMode, float forcedScale, bool selfTest) : base(forcedScale)
        {
            this.installDir = installDir;
            this.trayMode = trayMode;
            this.selfTest = selfTest;
            port = InstallLocator.ReadPort(installDir);
            Text = "Deployer Control";
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            BuildUi();
            if (!selfTest)
            {
                CreateTray();
                healthTimer = new System.Windows.Forms.Timer();
                healthTimer.Interval = 5000;
                healthTimer.Tick += delegate { PollHealth(); };
                healthTimer.Start();
                statusTimer = new System.Windows.Forms.Timer();
                statusTimer.Interval = 30000;
                statusTimer.Tick += delegate { if (Visible) RefreshStatus(); };
                statusTimer.Start();
                animTimer = new System.Windows.Forms.Timer();
                animTimer.Interval = 80;
                animTimer.Tick += delegate { if (Visible && (IsBusy || status == null) && activityIcon != null) activityIcon.Invalidate(); if (heroIcon != null && heroIcon.Kind == IconKind.Spinner) heroIcon.Invalidate(); };
                animTimer.Start();
                PollHealth();
                RefreshStatus();
            }
            Rectangle wa = Screen.FromPoint(Cursor.Position).WorkingArea;
            Location = new Point(wa.Left + Math.Max(0, (wa.Width - Width) / 2), wa.Top + Math.Max(0, (wa.Height - Height) / 2));
        }

        internal bool IsBusy { get { return runner != null; } }

        protected override void SetVisibleCore(bool value)
        {
            // In tray mode the window starts hidden.
            if (trayMode && !IsHandleCreated && !selfTest)
            {
                CreateHandle();
                value = false;
            }
            base.SetVisibleCore(value);
        }

        // ------------------------------------------------------------------ layout

        protected override void BuildUi()
        {
            int w = ui.S(DesignWidth), h = ui.S(DesignHeight);
            ClientSize = new Size(w, h);
            int pad = ui.S(28);
            int cw = w - pad * 2;
            tiles.Clear();

            LogoMark logo = new LogoMark(ui);
            logo.Bounds = new Rectangle(pad, ui.S(24), ui.S(44), ui.S(44));
            Controls.Add(logo);
            TextBlock title = new TextBlock(ui, "Deployer Control", ui.SemiBold(16f), Theme.Text);
            title.SingleLine = true;
            title.LayoutAt(pad + ui.S(58), ui.S(22), ui.S(360));
            Controls.Add(title);
            TextBlock sub = new TextBlock(ui, SubtitleText(), ui.Font(9.5f), Theme.TextSubtle);
            sub.SingleLine = true;
            sub.Name = "subtitle";
            sub.LayoutAt(pad + ui.S(58), ui.S(22) + ui.SemiBold(16f).Height + ui.S(1), cw - ui.S(220));
            Controls.Add(sub);
            pill = new StatusPill(ui);
            Controls.Add(pill);

            Rule rule = new Rule(Theme.Border);
            rule.Bounds = new Rectangle(0, ui.S(92), w, Math.Max(1, ui.S(1)));
            Controls.Add(rule);

            // Hero status card
            int y = ui.S(112);
            int heroH = ui.S(92);
            hero = new Card(ui, Theme.NeutralSoft, Color.Empty);
            hero.Radius = 12;
            hero.Bounds = new Rectangle(pad, y, cw, heroH);
            heroIcon = new IconBadge(ui, IconKind.Spinner, Theme.Accent, false);
            heroIcon.Bounds = new Rectangle(ui.S(22), (heroH - ui.S(40)) / 2, ui.S(40), ui.S(40));
            hero.Controls.Add(heroIcon);
            openButton = new FlatButton(ui, "Open Deployer", ButtonStyle.Primary);
            int ow = openButton.PreferredWidth(ui.S(150));
            openButton.Bounds = new Rectangle(cw - ow - ui.S(22), (heroH - ui.S(42)) / 2, ow, ui.S(42));
            openButton.Click += delegate { OpenDashboard(); };
            hero.Controls.Add(openButton);
            int textLeft = ui.S(80);
            int textWidth = cw - textLeft - ow - ui.S(40);
            heroTitle = new TextBlock(ui, "", ui.SemiBold(13f), Theme.Text);
            heroTitle.SingleLine = true;
            heroText = new TextBlock(ui, "", ui.Font(9.5f), Theme.TextMuted);
            heroText.SingleLine = true;
            int block = ui.SemiBold(13f).Height + ui.S(2) + ui.Font(9.5f).Height;
            heroTitle.LayoutAt(textLeft, (heroH - block) / 2, textWidth);
            heroText.LayoutAt(textLeft, (heroH - block) / 2 + ui.SemiBold(13f).Height + ui.S(2), textWidth);
            hero.Controls.Add(heroTitle);
            hero.Controls.Add(heroText);
            Controls.Add(hero);
            y += heroH + ui.S(24);

            // Services
            TextBlock servicesLabel = new TextBlock(ui, "Services", ui.SemiBold(10.5f), Theme.Text);
            servicesLabel.SingleLine = true;
            servicesLabel.LayoutAt(pad, y, ui.S(200));
            Controls.Add(servicesLabel);
            updatedText = new TextBlock(ui, "", ui.Font(9f), Theme.TextSubtle);
            updatedText.SingleLine = true;
            updatedText.RightAlign = true;
            int uw = ui.S(260);
            updatedText.LayoutAt(pad + cw - uw, y + (ui.SemiBold(10.5f).Height - ui.Font(9f).Height) / 2, uw);
            Controls.Add(updatedText);
            y += ui.SemiBold(10.5f).Height + ui.S(10);
            int gap = ui.S(12);
            int tileW = (cw - gap * (ServiceColumns - 1)) / ServiceColumns;
            int tileH = ui.S(58);
            int tileRows = (ServiceOrder.Length + ServiceColumns - 1) / ServiceColumns;
            for (int i = 0; i < ServiceOrder.Length; i++)
            {
                ServiceTile t = new ServiceTile(ui);
                t.Bounds = new Rectangle(pad + (i % ServiceColumns) * (tileW + gap), y + (i / ServiceColumns) * (tileH + gap), tileW, tileH);
                tiles[ServiceOrder[i]] = t;
                Controls.Add(t);
            }
            y += tileH * tileRows + gap * (tileRows - 1) + ui.S(24);

            // Actions
            TextBlock actionsLabel = new TextBlock(ui, "Actions", ui.SemiBold(10.5f), Theme.Text);
            actionsLabel.SingleLine = true;
            actionsLabel.LayoutAt(pad, y, ui.S(200));
            Controls.Add(actionsLabel);
            y += ui.SemiBold(10.5f).Height + ui.S(10);
            int bh = ui.S(38);
            int x = pad;
            startButton = ActionButton("Start", ButtonStyle.Secondary, ref x, y, delegate { RunAction("Starting Deployer", "start"); });
            stopButton = ActionButton("Stop", ButtonStyle.Secondary, ref x, y, delegate { RunAction("Stopping Deployer", "stop"); });
            restartButton = ActionButton("Restart", ButtonStyle.Secondary, ref x, y, delegate { RunAction("Restarting Deployer", "restart"); });
            x += ui.S(14);
            backupButton = ActionButton("Back up now", ButtonStyle.Secondary, ref x, y, delegate { RunAction("Backing up", "backup"); });
            updateButton = ActionButton("Update", ButtonStyle.Secondary, ref x, y, delegate { ConfirmUpdate(); });
            y += bh + ui.S(10);
            x = pad;
            ActionButton("View logs", ButtonStyle.Secondary, ref x, y, delegate { ShowLogs(); });
            ActionButton("Open install folder", ButtonStyle.Secondary, ref x, y, delegate { Shell.OpenUrl(installDir); });
            settingsButton = ActionButton("Settings", ButtonStyle.Secondary, ref x, y, delegate { ShowSettings(); });
            deviceButton = ActionButton(deviceBusy ? "Checking…" : "Host device", ButtonStyle.Secondary, ref x, y, delegate { ShowDevice(); });
            uninstallButton = new FlatButton(ui, "Uninstall", ButtonStyle.DangerGhost);
            int unw = uninstallButton.PreferredWidth(ui.S(96));
            uninstallButton.Bounds = new Rectangle(pad + cw - unw, y, unw, bh);
            uninstallButton.Click += delegate { StartUninstall(); };
            Controls.Add(uninstallButton);

            // Activity bar
            int barH = ui.S(58);
            Panel bar = new Panel();
            bar.BackColor = Theme.SurfaceAlt;
            bar.Bounds = new Rectangle(0, h - barH, w, barH);
            Rule barRule = new Rule(Theme.Border);
            barRule.Bounds = new Rectangle(0, 0, w, Math.Max(1, ui.S(1)));
            bar.Controls.Add(barRule);
            activityIcon = new IconBadge(ui, IconKind.Check, Theme.Success, false);
            activityIcon.Bounds = new Rectangle(pad, (barH - ui.S(20)) / 2, ui.S(20), ui.S(20));
            bar.Controls.Add(activityIcon);
            activityText = new TextBlock(ui, "", ui.Font(9.5f), Theme.TextMuted);
            activityText.SingleLine = true;
            activityText.LayoutAt(pad + ui.S(30), (barH - ui.Font(9.5f).Height) / 2, cw - ui.S(170));
            bar.Controls.Add(activityText);
            FlatButton details = new FlatButton(ui, "Show details", ButtonStyle.Link);
            details.FontPoints = 9.5f;
            int dw = Ui.MeasureWidth(details.Text, ui.SemiBold(9.5f)) + ui.S(6);
            details.Bounds = new Rectangle(pad + cw - dw, (barH - ui.S(24)) / 2, dw, ui.S(24));
            details.Click += delegate { ShowOutput(); };
            details.Name = "details";
            bar.Controls.Add(details);
            Controls.Add(bar);

            UpdateView();
        }

        FlatButton ActionButton(string text, ButtonStyle style, ref int x, int y, EventHandler click)
        {
            FlatButton b = new FlatButton(ui, text, style);
            int bw = b.PreferredWidth(ui.S(92));
            b.Bounds = new Rectangle(x, y, bw, ui.S(38));
            b.Click += click;
            Controls.Add(b);
            x += bw + ui.S(10);
            return b;
        }

        string SubtitleText()
        {
            string s = "http://localhost:" + port;
            if (status != null && status.Installed)
            {
                s += "  ·  " + StatusSnapshot.RuntimeLabel(status.Runtime);
                if (!string.IsNullOrEmpty(status.Version)) s += "  ·  " + status.Version;
            }
            return s;
        }

        internal RunState State
        {
            get
            {
                if (IsBusy) return RunState.Busy;
                if (healthy) return RunState.Running;
                if (status == null && !healthKnown) return RunState.Checking;
                if (status == null) return RunState.Checking;
                bool anyRunning = status.Services.Any(s => s.State == "running");
                if (anyRunning)
                {
                    if ((DateTime.Now - lastStartRequest).TotalMinutes < 5 || status.Services.Any(s => s.Health == "starting"))
                        return RunState.Starting;
                    return RunState.NotResponding;
                }
                return RunState.Stopped;
            }
        }

        internal void UpdateView()
        {
            if (pill == null) return;
            RunState st = State;
            string pillText;
            Color color;
            IconKind icon;
            string title, text;
            Color heroFill;
            switch (st)
            {
                case RunState.Running:
                    pillText = "Running"; color = Theme.Success; icon = IconKind.Check; heroFill = Theme.SuccessSoft;
                    title = "Deployer is running";
                    text = "Everything is working. Open it in your browser at http://localhost:" + port;
                    break;
                case RunState.Starting:
                    pillText = "Starting"; color = Theme.Warn; icon = IconKind.Spinner; heroFill = Theme.WarnSoft;
                    title = "Deployer is starting";
                    text = "This can take a few minutes after the PC starts.";
                    break;
                case RunState.NotResponding:
                    pillText = "Not responding"; color = Theme.Danger; icon = IconKind.Warn; heroFill = Theme.DangerSoft;
                    title = "Deployer isn't responding";
                    text = "Try Restart. If that doesn't help, View logs shows what went wrong.";
                    break;
                case RunState.Stopped:
                    pillText = "Stopped"; color = Theme.Neutral; icon = IconKind.Dot; heroFill = Theme.NeutralSoft;
                    title = "Deployer is stopped";
                    text = "Click Start to run it again. Your data is safe.";
                    break;
                case RunState.Busy:
                    pillText = actionVerb; color = Theme.Accent; icon = IconKind.Spinner; heroFill = Theme.AccentSoft;
                    title = actionName + "…";
                    text = string.IsNullOrEmpty(transient) ? "Please wait." : transient;
                    break;
                default:
                    pillText = "Checking"; color = Theme.Neutral; icon = IconKind.Spinner; heroFill = Theme.NeutralSoft;
                    title = "Checking Deployer…";
                    text = "Looking at the services on this PC.";
                    break;
            }
            pill.Label = pillText;
            pill.Color = color;
            int pw = pill.PreferredWidth();
            pill.Bounds = new Rectangle(ClientSize.Width - ui.S(28) - pw, ui.S(30), pw, ui.S(30));
            pill.Invalidate();
            hero.Fill = heroFill;
            hero.Invalidate();
            heroIcon.Kind = icon;
            heroIcon.Color = color;
            heroIcon.Invalidate();
            heroTitle.Text = title;
            heroText.Text = text;
            foreach (Control c in Controls)
            {
                TextBlock tb = c as TextBlock;
                if (tb != null && tb.Name == "subtitle") tb.Text = SubtitleText();
            }

            bool busy = IsBusy;
            startButton.Enabled = !busy && st != RunState.Running;
            stopButton.Enabled = !busy && st != RunState.Stopped;
            restartButton.Enabled = !busy;
            backupButton.Enabled = !busy && st == RunState.Running;
            updateButton.Enabled = !busy;
            settingsButton.Enabled = !busy && status != null && status.Installed;
            deviceButton.Enabled = !busy && !deviceBusy && st == RunState.Running;
            uninstallButton.Enabled = !busy;
            openButton.Enabled = st == RunState.Running || st == RunState.Starting || st == RunState.NotResponding;

            foreach (string name in ServiceOrder)
            {
                ServiceTile t = tiles[name];
                t.Title = FriendlyService(name);
                ServiceInfo info = status == null ? null : status.Services.FirstOrDefault(s => s.Name == name);
                if (status == null)
                {
                    t.StateText = "Checking…";
                    t.Dot = Theme.Neutral;
                }
                else if (name == "mongodb" && !status.ManagedMongodb)
                {
                    t.StateText = "Off (CPU has no AVX)";
                    t.Dot = Theme.Neutral;
                }
                else if (name == "tunnel" && (info == null || (info.State != "running" && info.State != "restarting")))
                {
                    // The connector only runs while remote access is enabled in the dashboard.
                    t.StateText = "Off";
                    t.Dot = Theme.Neutral;
                }
                else if (info == null)
                {
                    t.StateText = status.Engine ? "Not created" : "Stopped";
                    t.Dot = Theme.Neutral;
                }
                else if (info.State == "running")
                {
                    if (info.Health == "unhealthy") { t.StateText = "Unhealthy"; t.Dot = Theme.Danger; }
                    else if (info.Health == "starting") { t.StateText = "Starting…"; t.Dot = Theme.Warn; }
                    else { t.StateText = info.Health == "healthy" ? "Healthy" : "Running"; t.Dot = Theme.Success; }
                }
                else if (info.State == "restarting")
                {
                    t.StateText = "Restarting…";
                    t.Dot = Theme.Warn;
                }
                else
                {
                    t.StateText = "Stopped";
                    t.Dot = Theme.Neutral;
                }
                t.Invalidate();
            }
            updatedText.Text = status == null ? "" : "Updated " + status.Taken.ToString("t");

            if (busy)
            {
                activityIcon.Kind = IconKind.Spinner;
                activityIcon.Color = Theme.Accent;
                activityText.Text = actionName + "… Show details to follow along.";
            }
            else if (!string.IsNullOrEmpty(lastResult))
            {
                activityIcon.Kind = lastResultOk ? IconKind.Check : IconKind.Cross;
                activityIcon.Color = lastResultOk ? Theme.Success : Theme.Danger;
                activityText.Text = lastResult;
            }
            else
            {
                activityIcon.Kind = IconKind.Info;
                activityIcon.Color = Theme.TextDisabled;
                activityText.Text = "Install folder: " + installDir;
            }
            activityIcon.Invalidate();
            UpdateTray(st, pillText);
        }

        static string FriendlyService(string name)
        {
            switch (name)
            {
                case "caddy": return "Web server";
                case "api": return "API";
                case "dashboard": return "Dashboard";
                case "worker": return "Background jobs";
                case "mariadb": return "SQL database";
                case "mongodb": return "NoSQL database";
                case "redis": return "Cache";
                case "tunnel": return "Remote access";
                default: return name;
            }
        }

        // ------------------------------------------------------------------ polling

        void PollHealth()
        {
            if (healthBusy) return;
            healthBusy = true;
            int p = port;
            ThreadPool.QueueUserWorkItem(delegate
            {
                string body;
                bool ok = Internet.Health(p, out body);
                SafeInvoke(() =>
                {
                    healthBusy = false;
                    bool was = healthy;
                    healthy = ok;
                    healthKnown = true;
                    if (ok)
                    {
                        everHealthy = true;
                        failedPolls = 0;
                    }
                    else
                    {
                        failedPolls++;
                        bool quiet = IsBusy || (DateTime.Now - lastUserAction).TotalMinutes < 3;
                        if (everHealthy && failedPolls == 2 && !quiet && tray != null)
                        {
                            tray.ShowBalloonTip(10000, "Deployer stopped",
                                "Deployer is no longer responding. Open Deployer Control to start it again.", ToolTipIcon.Warning);
                            RefreshStatus();
                        }
                    }
                    if (was != ok) RefreshStatus();
                    UpdateView();
                });
            });
        }

        void RefreshStatus()
        {
            if (statusBusy || selfTest) return;
            statusBusy = true;
            string script = DeployerCli.ScriptFor(installDir, ref extractedRoot);
            string args = ProcessUtil.JoinArgs(ScriptRunner.ScriptArgs(script, new[] { "status", "-Json", "-InstallDir", installDir }));
            ThreadPool.QueueUserWorkItem(delegate
            {
                ProcessResult r = ProcessUtil.Run(AppInfo.PowerShellExe, args, 120000);
                StatusSnapshot snap = null;
                foreach (string line in r.StdOut.Split('\n'))
                {
                    Marker m = Marker.Parse(line);
                    if (m != null && m.Kind == MarkerKind.Status)
                    {
                        try { snap = StatusSnapshot.FromJson(m.Text); } catch (Exception) { }
                    }
                }
                SafeInvoke(() =>
                {
                    statusBusy = false;
                    if (snap != null)
                    {
                        status = snap;
                        if (snap.Installed && snap.Port != port) port = snap.Port;
                        if (snap.Healthy) { healthy = true; everHealthy = true; }
                    }
                    UpdateView();
                });
            });
        }

        void SafeInvoke(Action a)
        {
            try
            {
                if (IsDisposed || exiting) return;
                BeginInvoke(a);
            }
            catch (InvalidOperationException)
            {
            }
        }

        // ------------------------------------------------------------------ actions

        internal void RunAction(string name, params string[] args)
        {
            RunActions(name, new List<string[]> { args });
        }

        void RunActions(string name, List<string[]> commands)
        {
            if (IsBusy) return;
            lastUserAction = DateTime.Now;
            foreach (string[] c in commands) pending.Enqueue(c);
            actionName = name;
            actionVerb = VerbFor(commands[0][0]);
            actionLog.Length = 0;
            transient = "";
            lastResult = "";
            RunNext();
        }

        static string VerbFor(string command)
        {
            switch (command)
            {
                case "start": return "Starting";
                case "stop": return "Stopping";
                case "restart": return "Restarting";
                case "update": return "Updating";
                case "backup": return "Backing up";
                case "device": return "Detaching";
                default: return "Applying";
            }
        }

        void RunNext()
        {
            if (pending.Count == 0) return;
            string[] command = pending.Dequeue();
            if (command[0] == "start" || command[0] == "restart") lastStartRequest = DateTime.Now;
            List<string> args = new List<string>(command);
            args.Add("-InstallDir");
            args.Add(installDir);
            if (command[0] == "update" || command[0] == "uninstall" || command[0] == "device") args.Add("-Yes");
            string script;
            try
            {
                script = DeployerCli.ScriptFor(installDir, ref extractedRoot);
            }
            catch (Exception ex)
            {
                FinishAction(false, "Couldn't prepare the Deployer scripts: " + ex.Message);
                return;
            }
            actionLog.Append("> deployer ").Append(string.Join(" ", command)).Append("\r\n");
            runner = new ScriptRunner();
            runner.OutputLine += line => SafeInvoke(() => OnActionLine(line));
            runner.TransientLine += line => SafeInvoke(() => { transient = line.Trim(); UpdateView(); });
            string[] captured = command;
            runner.Exited += code => SafeInvoke(() => OnActionExited(captured, code));
            try
            {
                runner.Start(script, args);
            }
            catch (Exception ex)
            {
                runner = null;
                FinishAction(false, "Couldn't start PowerShell: " + ex.Message);
                return;
            }
            UpdateView();
        }

        void OnActionLine(string line)
        {
            if (Marker.Parse(line) != null) return;
            actionLog.Append(line).Append("\r\n");
            string t = line.Trim();
            if (t.Length > 0)
            {
                if (t.StartsWith("==> ")) t = t.Substring(4);
                if (t.StartsWith("[ok] ") || t.StartsWith("[!] ") || t.StartsWith("[x] ")) t = t.Substring(t.IndexOf(']') + 2);
                transient = t;
            }
            if (outputWindow != null && !outputWindow.IsDisposed) outputWindow.Append(line);
            UpdateView();
        }

        void OnActionExited(string[] command, int code)
        {
            runner = null;
            transient = "";
            actionLog.Append("(exit code ").Append(code).Append(")\r\n");
            if (code != 0)
            {
                pending.Clear();
                string error = LastError();
                FinishAction(false, actionName + " failed" + (error != null ? ": " + error : "."));
                if (Visible)
                {
                    ErrorDialog.Show(this, actionName + " didn't work",
                        (error ?? "Deployer reported a problem.") + " Click Copy details to share the full output when asking for help.",
                        actionLog.ToString());
                }
                else if (tray != null)
                {
                    tray.ShowBalloonTip(8000, actionName + " didn't work", error ?? "Open Deployer Control for details.", ToolTipIcon.Error);
                }
                return;
            }
            if (command[0] == "set-port")
            {
                int newPort;
                if (int.TryParse(command[1], out newPort))
                {
                    port = newPort;
                    try { Integration.UpdateDashboardShortcuts(installDir, newPort); } catch (Exception) { }
                }
            }
            if (pending.Count > 0)
            {
                RunNext();
                return;
            }
            FinishAction(true, DoneText(command[0]));
        }

        string DoneText(string command)
        {
            string time = DateTime.Now.ToString("t");
            switch (command)
            {
                case "start": return "Deployer started at " + time;
                case "stop": return "Deployer stopped at " + time + ". Your data is safe.";
                case "restart": return "Deployer restarted at " + time;
                case "update": return "Deployer was updated at " + time;
                case "backup": return "Backup finished at " + time + " (in the backups folder)";
                case "device": return "This PC was detached from its main Deployer at " + time;
                default: return "Settings saved at " + time;
            }
        }

        string LastError()
        {
            string[] lines = actionLog.ToString().Split(new[] { "\r\n" }, StringSplitOptions.None);
            for (int i = lines.Length - 1; i >= 0; i--)
            {
                string t = lines[i].Trim();
                if (t.StartsWith("[x] ")) return t.Substring(4);
            }
            return null;
        }

        void FinishAction(bool ok, string text)
        {
            lastResultOk = ok;
            lastResult = text;
            lastUserAction = DateTime.Now;
            UpdateView();
            RefreshStatus();
            PollHealth();
        }

        void ConfirmUpdate()
        {
            DialogResult r = MessageDialog.Ask(this, "Update Deployer?",
                "Deployer downloads the latest release, takes a backup first and restarts. Your data and settings are kept. It is unavailable for a few minutes.",
                IconKind.Info, Theme.Accent, "Update now", ButtonStyle.Primary, "Not now");
            if (r == DialogResult.Yes) RunAction("Updating Deployer", "update");
        }

        void OpenDashboard()
        {
            Shell.OpenUrl("http://localhost:" + port + "/");
        }

        void ShowOutput()
        {
            if (outputWindow == null || outputWindow.IsDisposed)
            {
                outputWindow = new OutputWindow("Deployer Control — details", 0);
                outputWindow.SetText(actionLog.Length > 0 ? actionLog.ToString() : "No actions yet. Output of Start, Stop, Update, Back up and Settings appears here.");
                outputWindow.PlaceCentered(this);
                outputWindow.Show(this);
            }
            else
            {
                outputWindow.Activate();
            }
        }

        void ShowLogs()
        {
            LogWindow w = new LogWindow(installDir, 0);
            w.PlaceCentered(this);
            w.Show(this);
        }

        void ShowSettings()
        {
            if (status == null) return;
            using (SettingsDialog d = new SettingsDialog(port, status.Lan, status.KeepAwake, status.Autostart, 0))
            {
                d.OpenSignInApps = ShowSignInApps;
                d.PlaceCentered(this);
                if (d.ShowDialog(this) != DialogResult.OK) return;
                List<string[]> commands = new List<string[]>();
                if (d.Port != port) commands.Add(new[] { "set-port", d.Port.ToString() });
                if (d.Lan != status.Lan) commands.Add(new[] { "lan", d.Lan ? "on" : "off" });
                if (d.KeepAwake != status.KeepAwake) commands.Add(new[] { "keepawake", d.KeepAwake ? "on" : "off" });
                if (d.Autostart != status.Autostart) commands.Add(new[] { "autostart", d.Autostart ? "on" : "off" });
                if (commands.Count > 0) RunActions("Applying settings", commands);
            }
        }

        void ShowSignInApps(Form owner)
        {
            string script;
            try
            {
                script = DeployerCli.ScriptFor(installDir, ref extractedRoot);
            }
            catch (Exception ex)
            {
                ErrorDialog.Show(owner, "Couldn't open sign-in apps", "Couldn't prepare the Deployer scripts.", ex.ToString());
                return;
            }
            using (SignInAppsDialog d = new SignInAppsDialog(script, installDir, 0))
            {
                d.PlaceCentered(owner);
                d.ShowDialog(owner);
            }
        }

        // ------------------------------------------------------------------ host device

        void ShowDevice()
        {
            if (IsBusy || deviceBusy) return;
            deviceBusy = true;
            deviceButton.Text = "Checking…";
            UpdateView();
            string script = DeployerCli.ScriptFor(installDir, ref extractedRoot);
            string args = ProcessUtil.JoinArgs(ScriptRunner.ScriptArgs(script, new[] { "device", "status", "-InstallDir", installDir }));
            ThreadPool.QueueUserWorkItem(delegate
            {
                ProcessResult r = ProcessUtil.Run(AppInfo.PowerShellExe, args, 120000);
                SafeInvoke(() =>
                {
                    deviceBusy = false;
                    deviceButton.Text = "Host device";
                    UpdateView();
                    IDictionary<string, object> d = r.ExitCode == 0 ? ParseDeviceJson(r.StdOut) : null;
                    if (d == null)
                    {
                        ErrorDialog.Show(this, "Couldn't read the device status",
                            "Make sure Deployer is running, then try again.", r.StdOut + "\r\n" + r.StdErr);
                        return;
                    }
                    int hosted = Json.List(d, "hosted_sources").Count;
                    DialogResult result;
                    using (MessageDialog dialog = CreateDeviceDialog(d, 0))
                    {
                        dialog.PlaceCentered(this);
                        result = dialog.ShowDialog(this);
                    }
                    if (result == DialogResult.Abort) ConfirmDetach(Json.Str(d, "primary_url"), hosted);
                });
            });
        }

        static IDictionary<string, object> ParseDeviceJson(string text)
        {
            int a = text.IndexOf('{');
            int b = text.LastIndexOf('}');
            if (a < 0 || b < a) return null;
            try
            {
                return Json.Parse(text.Substring(a, b - a + 1)) as IDictionary<string, object>;
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>Shows "deployer device status" in plain words; Detach closes it with DialogResult.Abort.</summary>
        internal static MessageDialog CreateDeviceDialog(IDictionary<string, object> d, float scale)
        {
            List<DialogButton> buttons = new List<DialogButton>();
            if (Json.Str(d, "mode") != "host")
            {
                buttons.Add(new DialogButton("Close", ButtonStyle.Primary, DialogResult.OK));
                return new MessageDialog("This PC is a standalone Deployer",
                    "It isn't attached to another Deployer. To make it a host device for an existing Deployer, open the dashboard and go to Settings → Devices.",
                    IconKind.Devices, Theme.Accent, buttons, null, null, scale);
            }
            bool connected = Json.Bool(d, "connected");
            int hosted = Json.List(d, "hosted_sources").Count;
            string name = Json.Str(d, "device_name");
            string error = Json.Str(d, "last_error");
            StringBuilder text = new StringBuilder();
            text.Append("This PC hosts databases for the main Deployer at ").Append(Json.Str(d, "primary_url")).Append(".\n\n");
            if (name.Length > 0) text.Append("Device name: ").Append(name).Append('\n');
            text.Append("Connection: ").Append(connected ? "connected" : "not connected").Append('\n');
            if (!connected && error.Length > 0) text.Append("Last error: ").Append(error).Append('\n');
            text.Append("Databases hosted here: ").Append(hosted);
            buttons.Add(new DialogButton("Detach…", ButtonStyle.DangerGhost, DialogResult.Abort));
            buttons.Add(new DialogButton("Close", ButtonStyle.Primary, DialogResult.OK));
            return new MessageDialog("Host device", text.ToString(), IconKind.Devices, connected ? Theme.Success : Theme.Warn,
                buttons, null, null, scale);
        }

        void ConfirmDetach(string primaryUrl, int hosted)
        {
            string message = hosted > 0
                ? "This PC still hosts " + hosted + " database(s). They stay on this PC, but the main Deployer can't use them until this PC is attached again. If you can, move them to another host from the main Deployer first."
                : "This PC forgets " + primaryUrl + ". The main Deployer shows it as offline until its owner removes it there.";
            DialogResult r = MessageDialog.Ask(this, "Detach this PC?", message, IconKind.Warn, Theme.Danger,
                "Detach", ButtonStyle.Danger, "Cancel");
            if (r != DialogResult.Yes) return;
            if (hosted > 0) RunAction("Detaching this device", "device", "detach", "-Force");
            else RunAction("Detaching this device", "device", "detach");
        }

        void StartUninstall()
        {
            try
            {
                Program.LaunchUninstaller(installDir);
                ExitApp();
            }
            catch (Exception ex)
            {
                ErrorDialog.Show(this, "Couldn't start the uninstaller", "Try again, or remove Deployer from Settings > Apps.", ex.ToString());
            }
        }

        // ------------------------------------------------------------------ tray

        void CreateTray()
        {
            trayMenu = new ContextMenuStrip();
            trayMenu.Font = new Font("Segoe UI", 9f);
            trayStatusItem = new ToolStripMenuItem("Checking Deployer…");
            trayStatusItem.Enabled = false;
            trayMenu.Items.Add(trayStatusItem);
            trayMenu.Items.Add(new ToolStripSeparator());
            ToolStripMenuItem open = new ToolStripMenuItem("Open Deployer", null, delegate { OpenDashboard(); });
            open.Font = new Font(trayMenu.Font, FontStyle.Bold);
            trayMenu.Items.Add(open);
            trayMenu.Items.Add(new ToolStripMenuItem("Deployer Control", null, delegate { ShowWindow(); }));
            trayMenu.Items.Add(new ToolStripSeparator());
            trayMenu.Items.Add(new ToolStripMenuItem("Start", null, delegate { RunAction("Starting Deployer", "start"); }));
            trayMenu.Items.Add(new ToolStripMenuItem("Stop", null, delegate { RunAction("Stopping Deployer", "stop"); }));
            trayMenu.Items.Add(new ToolStripMenuItem("Restart", null, delegate { RunAction("Restarting Deployer", "restart"); }));
            trayMenu.Items.Add(new ToolStripSeparator());
            trayMenu.Items.Add(new ToolStripMenuItem("Back up now", null, delegate { RunAction("Backing up", "backup"); }));
            trayMenu.Items.Add(new ToolStripMenuItem("Update…", null, delegate { ShowWindow(); ConfirmUpdate(); }));
            trayMenu.Items.Add(new ToolStripSeparator());
            trayMenu.Items.Add(new ToolStripMenuItem("Exit Deployer Control", null, delegate { ExitApp(); }));

            tray = new NotifyIcon();
            tray.Icon = AppIcon.Small();
            tray.Text = "Deployer";
            tray.ContextMenuStrip = trayMenu;
            tray.Visible = trayMode;
            tray.DoubleClick += delegate { ShowWindow(); };
            tray.BalloonTipClicked += delegate { ShowWindow(); };
        }

        void UpdateTray(RunState st, string label)
        {
            if (tray == null) return;
            string text = "Deployer: " + label.ToLowerInvariant();
            tray.Text = text.Length > 63 ? text.Substring(0, 63) : text;
            trayStatusItem.Text = "Deployer is " + (st == RunState.Busy ? label.ToLowerInvariant() + "…" : label.ToLowerInvariant());
            bool busy = IsBusy;
            foreach (ToolStripItem item in trayMenu.Items)
            {
                if (item.Text == "Start") item.Enabled = !busy && st != RunState.Running;
                if (item.Text == "Stop") item.Enabled = !busy && st != RunState.Stopped;
                if (item.Text == "Restart" || item.Text == "Update…") item.Enabled = !busy;
                if (item.Text == "Back up now") item.Enabled = !busy && st == RunState.Running;
            }
        }

        public void ShowWindow()
        {
            if (!Visible) Show();
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Activate();
            RefreshStatus();
        }

        void ExitApp()
        {
            exiting = true;
            if (tray != null)
            {
                tray.Visible = false;
                tray.Dispose();
            }
            Close();
            Application.Exit();
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!exiting && trayMode && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                Hide();
                if (!shownTrayHint && tray != null)
                {
                    shownTrayHint = true;
                    tray.ShowBalloonTip(5000, "Deployer Control is still here", "It keeps watching Deployer. Right-click this icon for actions.", ToolTipIcon.Info);
                }
                return;
            }
            if (!exiting && IsBusy && e.CloseReason == CloseReason.UserClosing)
            {
                DialogResult r = MessageDialog.Ask(this, actionName + " is still running",
                    "Closing Deployer Control now doesn't stop it cleanly. Wait until it finishes?",
                    IconKind.Warn, Theme.Warn, "Close anyway", ButtonStyle.Danger, "Wait");
                if (r != DialogResult.Yes)
                {
                    e.Cancel = true;
                    return;
                }
            }
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            exiting = true;
            if (healthTimer != null) healthTimer.Stop();
            if (statusTimer != null) statusTimer.Stop();
            if (animTimer != null) animTimer.Stop();
            if (tray != null)
            {
                tray.Visible = false;
                tray.Dispose();
                tray = null;
            }
            Payload.Cleanup(extractedRoot);
            base.OnFormClosed(e);
        }

        // ------------------------------------------------------------------ self-test support

        internal void ApplySample(StatusSnapshot snapshot, bool isHealthy, string busyAction, string result, bool resultOk)
        {
            status = snapshot;
            healthy = isHealthy;
            healthKnown = true;
            lastResult = result ?? "";
            lastResultOk = resultOk;
            if (busyAction != null)
            {
                actionName = busyAction;
                actionVerb = "Backing up";
                transient = "MariaDB dumped to mariadb.sql";
                runner = new ScriptRunner();
            }
            UpdateView();
        }
    }

    /// <summary>Settings: port, LAN access, keep awake, start at sign-in.</summary>
    class SettingsDialog : ThemedForm
    {
        public int Port { get; private set; }
        public bool Lan { get; private set; }
        public bool KeepAwake { get; private set; }
        public bool Autostart { get; private set; }
        /// <summary>Opens the sign-in apps dialog over this one (set by Deployer Control).</summary>
        public Action<Form> OpenSignInApps;
        readonly int originalPort;
        InputBox portInput;
        TextBlock portHint;
        FlatButton save;

        public SettingsDialog(int port, bool lan, bool keepAwake, bool autostart, float forcedScale) : base(forcedScale)
        {
            Port = originalPort = port;
            Lan = lan;
            KeepAwake = keepAwake;
            Autostart = autostart;
            Text = "Deployer settings";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ShowInTaskbar = false;
            BuildUi();
        }

        protected override void BuildUi()
        {
            int w = ui.S(520);
            int pad = ui.S(28);
            int cw = w - pad * 2;
            int y = ui.S(26);
            TextBlock title = new TextBlock(ui, "Settings", ui.SemiBold(16f), Theme.Text);
            y += title.LayoutAt(pad, y, cw) + ui.S(4);
            Controls.Add(title);
            TextBlock sub = new TextBlock(ui, "Changes are applied right away. Deployer may restart briefly.", ui.Font(10f), Theme.TextMuted);
            y += sub.LayoutAt(pad, y, cw) + ui.S(20);
            Controls.Add(sub);

            TextBlock portLabel = new TextBlock(ui, "Port", ui.SemiBold(10f), Theme.Text);
            y += portLabel.LayoutAt(pad, y, cw) + ui.S(6);
            Controls.Add(portLabel);
            int inputH = ui.S(36);
            portInput = new InputBox(ui, Port.ToString());
            portInput.Box.MaxLength = 5;
            portInput.Bounds = new Rectangle(pad, y, ui.S(96), inputH);
            portInput.Box.TextChanged += delegate { Validate2(); };
            Controls.Add(portInput);
            portHint = new TextBlock(ui, "", ui.Font(9.5f), Theme.TextMuted);
            portHint.SingleLine = true;
            portHint.LayoutAt(pad + ui.S(110), y + (inputH - ui.Font(9.5f).Height) / 2, cw - ui.S(110));
            Controls.Add(portHint);
            y += inputH + ui.S(12);

            Rule rule = new Rule(Theme.Border);
            rule.Bounds = new Rectangle(pad, y, cw, Math.Max(1, ui.S(1)));
            Controls.Add(rule);
            y += ui.S(4);

            y = Toggle(y, cw, pad, "Let other devices on my network open Deployer",
                "Adds a firewall rule for private (home or work) networks only.", Lan, v => Lan = v);
            y = Toggle(y, cw, pad, "Keep this PC awake while plugged in",
                "Stops sleep and hibernate while the charger is connected. Turning it off restores your previous settings.", KeepAwake, v => KeepAwake = v);
            y = Toggle(y, cw, pad, "Start Deployer when I sign in to Windows",
                "Also shows the Deployer icon next to the clock.", Autostart, v => Autostart = v);

            Rule signInRule = new Rule(Theme.Border);
            signInRule.Bounds = new Rectangle(pad, y + ui.S(6), cw, Math.Max(1, ui.S(1)));
            Controls.Add(signInRule);
            y += ui.S(18);
            FlatButton signIn = new FlatButton(ui, "Set up…", ButtonStyle.Secondary);
            int siw = signIn.PreferredWidth(ui.S(96));
            TextBlock signInTitle = new TextBlock(ui, "Sign-in apps (Google & GitHub)", ui.SemiBold(10f), Theme.Text);
            int th = signInTitle.LayoutAt(pad, y, cw - siw - ui.S(16)) + ui.S(2);
            Controls.Add(signInTitle);
            TextBlock signInText = new TextBlock(ui, "Let people sign in with Google or GitHub: enter your OAuth Client IDs and secrets.", ui.Font(9.5f), Theme.TextMuted);
            th += signInText.LayoutAt(pad, y + th, cw - siw - ui.S(16));
            Controls.Add(signInText);
            int sbh = ui.S(34);
            signIn.Bounds = new Rectangle(pad + cw - siw, y + Math.Max(0, (th - sbh) / 2), siw, sbh);
            signIn.Click += delegate { if (OpenSignInApps != null) OpenSignInApps(this); };
            Controls.Add(signIn);
            y += Math.Max(th, sbh) + ui.S(18);

            Panel footer = new Panel();
            footer.BackColor = Theme.SurfaceAlt;
            int fh = ui.S(68);
            footer.Bounds = new Rectangle(0, y, w, fh);
            Rule fr = new Rule(Theme.Border);
            fr.Bounds = new Rectangle(0, 0, w, Math.Max(1, ui.S(1)));
            footer.Controls.Add(fr);
            int bh = ui.S(38);
            save = new FlatButton(ui, "Save", ButtonStyle.Primary);
            int sw = save.PreferredWidth(ui.S(96));
            save.Bounds = new Rectangle(w - pad - sw, (fh - bh) / 2, sw, bh);
            save.Click += delegate { if (Validate2()) { DialogResult = DialogResult.OK; Close(); } };
            footer.Controls.Add(save);
            FlatButton cancel = new FlatButton(ui, "Cancel", ButtonStyle.Secondary);
            int cwid = cancel.PreferredWidth(ui.S(96));
            cancel.Bounds = new Rectangle(w - pad - sw - ui.S(10) - cwid, (fh - bh) / 2, cwid, bh);
            cancel.Click += delegate { DialogResult = DialogResult.Cancel; Close(); };
            footer.Controls.Add(cancel);
            Controls.Add(footer);
            AcceptButton = save;
            CancelButton = cancel;
            ClientSize = new Size(w, y + fh);
            Validate2();
        }

        int Toggle(int y, int cw, int pad, string title, string description, bool value, Action<bool> set)
        {
            ToggleRow row = new ToggleRow(ui, title, description, value);
            row.Changed += delegate { set(row.On); };
            y += row.LayoutAt(pad, y, cw);
            Controls.Add(row);
            return y + ui.S(2);
        }

        bool Validate2()
        {
            int p;
            string error = null;
            if (!int.TryParse(portInput.Box.Text.Trim(), out p) || p < 1024 || p > 65535)
                error = "Enter a number from 1024 to 65535.";
            else if (p != originalPort && !Ports.IsFree(p))
                error = "Port " + p + " is used by another program.";
            if (error == null) Port = p;
            portHint.Text = error ?? "Deployer opens at http://localhost:" + (error == null ? p : originalPort);
            portHint.TextColor = error != null ? Theme.Danger : Theme.TextMuted;
            portHint.Invalidate();
            portInput.Invalid = error != null;
            if (save != null) save.Enabled = error == null;
            return error == null;
        }
    }

    /// <summary>Read-only text window for command output.</summary>
    class OutputWindow : ThemedForm
    {
        protected TextBox box;
        readonly string title;
        string text = "";
        protected Panel toolbar;

        public OutputWindow(string title, float forcedScale) : base(forcedScale)
        {
            this.title = title;
            Text = title;
            FormBorderStyle = FormBorderStyle.Sizable;
            MinimizeBox = true;
            MaximizeBox = true;
            BuildUi();
        }

        protected virtual int ToolbarHeight { get { return 0; } }
        protected virtual void BuildToolbar(Panel bar) { }

        protected override void BeforeRebuild()
        {
            if (box != null) text = box.Text;
        }

        protected override void BuildUi()
        {
            if (ClientSize.Width < ui.S(600)) ClientSize = new Size(ui.S(820), ui.S(520));
            MinimumSize = new Size(ui.S(420), ui.S(300));
            int th = ToolbarHeight > 0 ? ui.S(ToolbarHeight) : 0;
            if (th > 0)
            {
                toolbar = new Panel();
                toolbar.BackColor = Theme.SurfaceAlt;
                toolbar.Dock = DockStyle.Top;
                toolbar.Height = th;
                BuildToolbar(toolbar);
            }
            box = new TextBox();
            box.Multiline = true;
            box.ReadOnly = true;
            box.WordWrap = false;
            box.ScrollBars = Program.SelfTestMode ? ScrollBars.None : ScrollBars.Both; // scroll bars do not print off-screen
            box.BorderStyle = BorderStyle.None;
            box.BackColor = Theme.Surface;
            box.ForeColor = Theme.Text;
            box.Font = ui.Mono(9f);
            box.Dock = DockStyle.Fill;
            box.Text = text;
            Panel holder = new Panel();
            holder.Dock = DockStyle.Fill;
            holder.Padding = new Padding(ui.S(12), ui.S(8), ui.S(4), ui.S(4));
            holder.BackColor = Theme.Surface;
            holder.Controls.Add(box);
            Controls.Add(holder);
            if (toolbar != null) Controls.Add(toolbar);
        }

        public void SetText(string value)
        {
            box.Text = value;
            box.SelectionStart = box.TextLength;
            box.ScrollToCaret();
        }

        public void Append(string line)
        {
            if (box.TextLength > 600000) box.Text = box.Text.Substring(box.TextLength - 300000);
            box.AppendText(line + "\r\n");
        }
    }

    /// <summary>Live "deployer logs -Follow" viewer.</summary>
    class LogWindow : OutputWindow
    {
        readonly string installDir;
        ScriptRunner runner;
        string service = "";
        string extractedRoot;
        TextBlock stateText;

        public LogWindow(string installDir, float forcedScale) : base("Deployer logs", forcedScale)
        {
            this.installDir = installDir;
            if (forcedScale <= 0) Shown += delegate { StartTail(); };
        }

        protected override int ToolbarHeight { get { return 52; } }

        protected override void BuildToolbar(Panel bar)
        {
            TextBlock label = new TextBlock(ui, "Show logs for", ui.Font(9.5f), Theme.TextMuted);
            label.SingleLine = true;
            int lw = Ui.MeasureWidth(label.Text, ui.Font(9.5f)) + ui.S(4);
            label.LayoutAt(ui.S(16), (bar.Height - ui.Font(9.5f).Height) / 2, lw);
            bar.Controls.Add(label);
            int x = ui.S(26) + lw;
            int bh = ui.S(30);
            foreach (string name in new[] { "", "api", "worker", "dashboard", "caddy", "mariadb", "mongodb", "redis", "tunnel" })
            {
                FlatButton pill = new FlatButton(ui, name == "" ? "All" : name, name == service ? ButtonStyle.Primary : ButtonStyle.Secondary);
                pill.FontPoints = 9f;
                int bw = Math.Max(ui.S(44), Ui.MeasureWidth(pill.Text, ui.SemiBold(9f)) + ui.S(22));
                pill.Bounds = new Rectangle(x, (bar.Height - bh) / 2, bw, bh);
                string chosen = name;
                pill.Click += delegate
                {
                    if (chosen == service) return;
                    service = chosen;
                    SetText("");
                    Rebuild();
                    StartTail();
                };
                bar.Controls.Add(pill);
                x += bw + ui.S(6);
            }
            stateText = new TextBlock(ui, running ? "Live" : "Stopped", ui.Font(9f), Theme.TextSubtle);
            stateText.SingleLine = true;
            // The toolbar isn't docked yet, so size the label from the window width, not bar.Width.
            int stateW = Math.Max(ui.S(40), Math.Min(ui.S(120), ClientSize.Width - (x + ui.S(10)) - ui.S(12)));
            stateText.LayoutAt(x + ui.S(10), (bar.Height - ui.Font(9f).Height) / 2, stateW);
            bar.Controls.Add(stateText);
        }

        bool running = true;

        void StartTail()
        {
            StopTail();
            List<string> args = new List<string> { "logs" };
            if (service != "") args.Add(service);
            args.AddRange(new[] { "-Follow", "-Tail", "300", "-InstallDir", installDir });
            try
            {
                string script = DeployerCli.ScriptFor(installDir, ref extractedRoot);
                ScriptRunner r = new ScriptRunner();
                runner = r;
                r.OutputLine += line => Post(() => { if (runner == r) Append(line); });
                r.Exited += code => Post(() =>
                {
                    if (runner != r) return;
                    running = false;
                    if (stateText != null) stateText.Text = "Stopped";
                    Append("(The log stream ended. Deployer may not be running.)");
                });
                running = true;
                if (stateText != null) stateText.Text = "Live";
                r.Start(script, args);
            }
            catch (Exception ex)
            {
                Append("Couldn't read the logs: " + ex.Message);
            }
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

        void StopTail()
        {
            if (runner != null)
            {
                ScriptRunner r = runner;
                runner = null;
                ThreadPool.QueueUserWorkItem(delegate { r.Cancel(); });
            }
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            StopTail();
            Payload.Cleanup(extractedRoot);
            base.OnFormClosed(e);
        }
    }
}
