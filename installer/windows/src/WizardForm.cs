// The setup wizard: Welcome -> System check -> Docker -> Options -> Install -> Finish.
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
    enum WizardPage { Welcome, Checks, Docker, Options, Install, Reboot, Error, Finish }

    class StepRail : PaintedControl
    {
        public static readonly string[] Steps = { "Welcome", "System check", "Docker", "Options", "Install", "Finish" };
        public int Current { get; set; }
        public bool DryRun { get; set; }
        public bool Failed { get; set; }

        public StepRail(Ui ui) : base(ui)
        {
            BackColor = Theme.Rail;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (Pen border = new Pen(Theme.Border, Math.Max(1f, ui.Factor)))
                g.DrawLine(border, Width - ui.Factor * 0.5f, 0, Width - ui.Factor * 0.5f, Height);

            float logo = ui.S(38);
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            Logo.Draw(g, new RectangleF(ui.S(28), ui.S(30), logo, logo));
            g.PixelOffsetMode = PixelOffsetMode.Default;
            Font title = ui.SemiBold(14f);
            Font sub = ui.Font(9f);
            int tx = ui.S(28) + (int)logo + ui.S(12);
            int blockH = title.Height + sub.Height - ui.S(2);
            int ty = ui.S(30) + ((int)logo - blockH) / 2 - ui.S(1);
            TextRenderer.DrawText(g, "Deployer", title, new Point(tx, ty), Theme.Text, TextFormatFlags.NoPadding);
            TextRenderer.DrawText(g, "Setup", sub, new Point(tx + ui.S(1), ty + title.Height - ui.S(2)), Theme.TextSubtle, TextFormatFlags.NoPadding);

            int y = ui.S(118);
            int row = ui.S(50);
            float circle = ui.S(26);
            Font label = ui.Font(10f);
            Font labelOn = ui.SemiBold(10f);
            Font num = ui.SemiBold(9f);
            for (int i = 0; i < Steps.Length; i++)
            {
                bool done = i < Current;
                bool current = i == Current;
                RectangleF c = new RectangleF(ui.S(28), y + (row - circle) / 2f, circle, circle);
                if (i < Steps.Length - 1)
                {
                    using (Pen line = new Pen(done ? Theme.Accent : Theme.Border, Math.Max(1.5f, ui.Factor * 2f)))
                        g.DrawLine(line, c.Left + circle / 2f, c.Bottom + ui.S(4), c.Left + circle / 2f, c.Bottom + row - circle - ui.S(4));
                }
                if (current)
                {
                    RectangleF pill = new RectangleF(ui.S(16), y + ui.S(5), Width - ui.S(32), row - ui.S(10));
                    using (GraphicsPath p = Logo.RoundedRect(pill, ui.S(9)))
                    using (SolidBrush b = new SolidBrush(Color.White))
                        g.FillPath(b, p);
                    using (GraphicsPath p = Logo.RoundedRect(pill, ui.S(9)))
                    using (Pen pen = new Pen(Theme.Border, Math.Max(1f, ui.Factor)))
                        g.DrawPath(pen, p);
                }
                if (done)
                {
                    using (SolidBrush b = new SolidBrush(Theme.Accent)) g.FillEllipse(b, c);
                    Glyphs.Draw(g, c, IconKind.Check, Color.White);
                }
                else if (current && Failed)
                {
                    using (SolidBrush b = new SolidBrush(Theme.Danger)) g.FillEllipse(b, c);
                    Glyphs.Draw(g, c, IconKind.Cross, Color.White);
                }
                else
                {
                    using (SolidBrush b = new SolidBrush(current ? Theme.Accent : Theme.Surface)) g.FillEllipse(b, c);
                    if (!current)
                        using (Pen pen = new Pen(Theme.BorderStrong, Math.Max(1f, ui.Factor * 1.5f))) g.DrawEllipse(pen, c);
                    TextRenderer.DrawText(g, (i + 1).ToString(), num, Rectangle.Round(c), current ? Color.White : Theme.TextSubtle,
                        TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding | TextFormatFlags.SingleLine);
                }
                Font f = current ? labelOn : label;
                Color color = current ? Theme.Text : done ? Theme.TextMuted : Theme.TextSubtle;
                TextRenderer.DrawText(g, Steps[i], f, new Rectangle((int)c.Right + ui.S(12), y, Width - (int)c.Right - ui.S(20), row), color,
                    TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
                y += row;
            }

            int by = Height - ui.S(34);
            if (DryRun)
            {
                Font bf = ui.SemiBold(8.5f);
                string text = "TEST MODE: nothing is changed";
                int bw = Ui.MeasureWidth(text, bf) + ui.S(20);
                RectangleF br = new RectangleF(ui.S(24), by - ui.S(40), Math.Min(bw, Width - ui.S(40)), bf.Height + ui.S(10));
                using (GraphicsPath p = Logo.RoundedRect(br, br.Height / 2f))
                using (SolidBrush b = new SolidBrush(Theme.WarnSoft))
                    g.FillPath(b, p);
                TextRenderer.DrawText(g, text, bf, Rectangle.Round(br), Theme.WarnText,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding | TextFormatFlags.SingleLine);
            }
            TextRenderer.DrawText(g, "Version " + AppInfo.Version, ui.Font(8.5f), new Point(ui.S(28), by), Theme.TextSubtle, TextFormatFlags.NoPadding);
        }
    }

    class WizardForm : ThemedForm
    {
        public static readonly string[] DefaultStepNames =
        {
            "Checking this PC", "Getting Deployer files", "Setting up Docker", "Writing configuration",
            "Downloading container images", "Starting Deployer", "Waiting for Deployer to be ready",
            "Starting Deployer when you sign in", "Network and power settings", "Finishing up"
        };

        const int DesignWidth = 920;
        const int DesignHeight = 656;
        const int RailWidth = 244;

        // ---- model ----
        internal WizardPage page = WizardPage.Welcome;
        internal readonly bool dryRun;
        internal readonly bool resume;
        internal readonly bool selfTest;
        internal SetupOptions options = new SetupOptions();
        internal SystemReport report;
        internal bool checking;
        bool runtimeChosenByUser;
        bool portEditedByUser;
        internal string installedDir;
        internal int installedPort = -1;

        internal int step;
        internal int totalSteps = 10;
        internal string[] stepNames = (string[])DefaultStepNames.Clone();
        internal string stepText = "Preparing";
        internal string transient = "";
        internal readonly StringBuilder log = new StringBuilder();
        internal bool showDetails;
        internal double progress;
        internal DateTime stepStarted = DateTime.Now;
        internal DateTime installStarted = DateTime.Now;
        internal string errorMessage = "";
        internal string doneUrl = "";
        bool sawReboot, sawDone;
        internal ScriptRunner runner;
        string payloadRoot;
        System.Windows.Forms.Timer ticker;

        // ---- live controls ----
        Panel pageHost;
        StepRail rail;
        ProgressLine progressLine;
        TextBlock stepLabel, stepCount, transientLabel;
        TextBox logBox;
        List<CheckRow> stepRows;
        FlatButton nextButton;
        TextBlock portHint, dirHint;
        InputBox dirInput, portInput;

        public WizardForm(bool dryRun, bool resume, float forcedScale, bool selfTest) : base(forcedScale)
        {
            this.dryRun = dryRun;
            this.resume = resume;
            this.selfTest = selfTest;
            Text = dryRun ? "Deployer Setup (test mode)" : "Deployer Setup";
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            installedDir = InstallLocator.Find();
            if (installedDir != null)
            {
                options.InstallDir = installedDir;
                installedPort = InstallLocator.ReadPort(installedDir);
                options.Port = installedPort;
                LoadInstalledOptions();
            }
            if (resume)
            {
                string file = Path.Combine(Path.GetDirectoryName(AppInfo.ExePath), AppInfo.OptionsFileName);
                try
                {
                    options = SetupOptions.Load(file);
                    runtimeChosenByUser = true;
                    portEditedByUser = true;
                    page = WizardPage.Install;
                }
                catch (Exception)
                {
                    page = WizardPage.Welcome;
                }
            }
            if (!selfTest)
            {
                ticker = new System.Windows.Forms.Timer();
                ticker.Interval = 80;
                ticker.Tick += OnTick;
                ticker.Start();
            }
            BuildUi();
            if (!IsForcedScale) FitToScreen();
        }

        /// <summary>An update keeps the runtime and the choices made at install time (from runtime.json).</summary>
        void LoadInstalledOptions()
        {
            try
            {
                IDictionary<string, object> state = Json.Parse(File.ReadAllText(Path.Combine(installedDir, "runtime.json"))) as IDictionary<string, object>;
                if (state == null) return;
                string rt = Json.Str(state, "runtime");
                if (rt.Length > 0)
                {
                    options.Runtime = rt;
                    runtimeChosenByUser = true;
                }
                object lan, keepAwake;
                if (state.TryGetValue("lan", out lan)) options.EnableLan = Json.Bool(lan as IDictionary<string, object>, "enabled");
                if (state.TryGetValue("keepAwake", out keepAwake)) options.KeepAwake = Json.Bool(keepAwake as IDictionary<string, object>, "enabled");
                if (state.ContainsKey("autostart")) options.Autostart = Json.Bool(state, "autostart");
                options.DesktopShortcut = File.Exists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Deployer.lnk"));
            }
            catch (Exception)
            {
            }
        }

        void FitToScreen()
        {
            Rectangle wa = Screen.FromPoint(Cursor.Position).WorkingArea;
            Location = new Point(wa.Left + Math.Max(0, (wa.Width - Width) / 2), wa.Top + Math.Max(0, (wa.Height - Height) / 2));
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (selfTest) return;
            if (page == WizardPage.Install && resume) StartInstall();
        }

        int ContentLeft { get { return ui.S(48); } }
        int ContentWidth { get { return ui.S(DesignWidth - RailWidth - 96); } }

        protected override void BuildUi()
        {
            int w = ui.S(DesignWidth), h = ui.S(DesignHeight);
            // Very small screens: shrink to fit rather than hide the buttons.
            if (!IsForcedScale)
            {
                Rectangle wa = Screen.FromPoint(Cursor.Position).WorkingArea;
                int chromeH = SystemInformation.CaptionHeight + SystemInformation.FixedFrameBorderSize.Height * 2 + ui.S(8);
                if (h + chromeH > wa.Height && ui.Factor > 0.8f)
                {
                    ui = new Ui(Math.Max(0.75f, ui.Factor * (wa.Height - chromeH) / (float)(h)));
                    w = ui.S(DesignWidth);
                    h = ui.S(DesignHeight);
                    Font = ui.Font(9.5f);
                }
            }
            ClientSize = new Size(w, h);

            rail = new StepRail(ui);
            rail.Bounds = new Rectangle(0, 0, ui.S(RailWidth), h);
            rail.DryRun = dryRun;
            Controls.Add(rail);

            int footerH = ui.S(76);
            pageHost = new Panel();
            pageHost.BackColor = Theme.Surface;
            pageHost.Bounds = new Rectangle(rail.Width, 0, w - rail.Width, h - footerH);
            pageHost.AutoScroll = true;
            Controls.Add(pageHost);

            Panel footer = new Panel();
            footer.BackColor = Theme.Surface;
            footer.Bounds = new Rectangle(rail.Width, h - footerH, w - rail.Width, footerH);
            Rule rule = new Rule(Theme.Border);
            rule.Bounds = new Rectangle(0, 0, footer.Width, Math.Max(1, ui.S(1)));
            footer.Controls.Add(rule);
            Controls.Add(footer);

            BuildPage(footer);
        }

        void GoTo(WizardPage p)
        {
            page = p;
            Rebuild();
        }

        void BuildPage(Panel footer)
        {
            stepRows = null;
            progressLine = null;
            logBox = null;
            nextButton = null;
            switch (page)
            {
                case WizardPage.Welcome: rail.Current = 0; BuildWelcome(footer); break;
                case WizardPage.Checks: rail.Current = 1; BuildChecks(footer); break;
                case WizardPage.Docker: rail.Current = 2; BuildDocker(footer); break;
                case WizardPage.Options: rail.Current = 3; BuildOptions(footer); break;
                case WizardPage.Install: rail.Current = 4; BuildInstall(footer); break;
                case WizardPage.Reboot: rail.Current = 4; BuildReboot(footer); break;
                case WizardPage.Error: rail.Current = 4; rail.Failed = true; BuildError(footer); break;
                case WizardPage.Finish: rail.Current = 5; BuildFinish(footer); break;
            }
        }

        // ------------------------------------------------------------------ helpers

        int Header(string title, string subtitle)
        {
            int y = ui.S(38);
            TextBlock t = new TextBlock(ui, title, ui.SemiBold(19f), Theme.Text);
            y += t.LayoutAt(ContentLeft, y, ContentWidth);
            pageHost.Controls.Add(t);
            if (!string.IsNullOrEmpty(subtitle))
            {
                y += ui.S(6);
                TextBlock s = new TextBlock(ui, subtitle, ui.Font(10.5f), Theme.TextMuted);
                y += s.LayoutAt(ContentLeft, y, ContentWidth);
                pageHost.Controls.Add(s);
            }
            return y + ui.S(20);
        }

        FlatButton AddFooterButton(Panel footer, string text, ButtonStyle style, bool right, ref int edge, EventHandler onClick)
        {
            FlatButton b = new FlatButton(ui, text, style);
            int bw = b.PreferredWidth(ui.S(style == ButtonStyle.Ghost ? 84 : 112));
            int bh = ui.S(40);
            int by = (footer.Height - bh) / 2 + ui.S(1);
            if (right)
            {
                edge -= bw;
                b.Bounds = new Rectangle(edge, by, bw, bh);
                edge -= ui.S(10);
            }
            else
            {
                b.Bounds = new Rectangle(edge, by, bw, bh);
                edge += bw + ui.S(10);
            }
            b.Click += onClick;
            footer.Controls.Add(b);
            return b;
        }

        void StandardFooter(Panel footer, string nextText, bool showBack, EventHandler onNext)
        {
            int left = ContentLeft - ui.S(12);
            AddFooterButton(footer, "Cancel", ButtonStyle.Ghost, false, ref left, delegate { Close(); });
            int right = footer.Width - ContentLeft;
            nextButton = AddFooterButton(footer, nextText, ButtonStyle.Primary, true, ref right, onNext);
            if (showBack) AddFooterButton(footer, "Back", ButtonStyle.Secondary, true, ref right, delegate { GoBack(); });
            AcceptButton = nextButton;
        }

        void GoBack()
        {
            switch (page)
            {
                case WizardPage.Checks: GoTo(WizardPage.Welcome); break;
                case WizardPage.Docker: GoTo(WizardPage.Checks); break;
                case WizardPage.Options: GoTo(WizardPage.Docker); break;
            }
        }

        // ------------------------------------------------------------------ Welcome

        void BuildWelcome(Panel footer)
        {
            int y = Header("Welcome to Deployer", null);
            TextBlock lead = new TextBlock(ui,
                "Deployer turns this PC into your own private cloud: a dashboard where you and the people you invite create projects with SQL and NoSQL databases. Think Supabase and Vercel, running on your own computer.",
                ui.Font(11f), Theme.TextMuted);
            y += lead.LayoutAt(ContentLeft, y - ui.S(8), ContentWidth) + ui.S(22);
            pageHost.Controls.Add(lead);

            y = Feature(y, IconKind.Lock, "Private by design",
                "Nothing is shared with the Deployer authors \u2014 no accounts or keys needed. Every password is created on this PC.");
            y = Feature(y, IconKind.Heart, "Free and open source",
                "The recommended setup uses only free, open-source software. No trial, no sign-up.");
            y = Feature(y, IconKind.Clock, "Takes about 10\u201330 minutes",
                "Setup downloads what it needs (about 1\u20132 GB) and may ask to restart Windows once. You can keep using your PC meanwhile.");

            if (installedDir != null)
            {
                y += ui.S(4);
                y = Note(y, IconKind.Info, Theme.Accent, Theme.AccentSoft,
                    "Deployer is already installed in " + installedDir + ". Continuing updates it and keeps your data and settings.");
            }
            StandardFooter(footer, "Next", false, delegate { GoTo(WizardPage.Checks); });
        }

        int Feature(int y, IconKind icon, string title, string text)
        {
            int badge = ui.S(40);
            IconBadge b = new IconBadge(ui, icon, Theme.Accent, true);
            b.Bounds = new Rectangle(ContentLeft, y, badge, badge);
            pageHost.Controls.Add(b);
            int tx = ContentLeft + badge + ui.S(16);
            int tw = ContentWidth - badge - ui.S(16);
            TextBlock t = new TextBlock(ui, title, ui.SemiBold(10.5f), Theme.Text);
            int h = t.LayoutAt(tx, y + ui.S(1), tw);
            pageHost.Controls.Add(t);
            TextBlock d = new TextBlock(ui, text, ui.Font(10f), Theme.TextMuted);
            h += ui.S(3) + d.LayoutAt(tx, y + ui.S(1) + h + ui.S(3), tw);
            pageHost.Controls.Add(d);
            return y + Math.Max(badge, h) + ui.S(22);
        }

        int Note(int y, IconKind icon, Color color, Color fill, string text)
        {
            Card card = new Card(ui, fill, Color.Empty);
            int pad = ui.S(14);
            int iconSize = ui.S(22);
            TextBlock t = new TextBlock(ui, text, ui.Font(9.5f), Glyphs.Blend(color, Theme.Text, 0.45f));
            int th = t.LayoutAt(pad + iconSize + ui.S(10), pad, ContentWidth - pad * 2 - iconSize - ui.S(10));
            int ch = Math.Max(th, iconSize) + pad * 2;
            t.Top = (ch - th) / 2;
            card.Bounds = new Rectangle(ContentLeft, y, ContentWidth, ch);
            IconBadge ib = new IconBadge(ui, icon, color, false);
            ib.Bounds = new Rectangle(pad, (ch - iconSize) / 2, iconSize, iconSize);
            card.Controls.Add(ib);
            card.Controls.Add(t);
            pageHost.Controls.Add(card);
            return y + ch + ui.S(16);
        }

        // ------------------------------------------------------------------ System check

        void BuildChecks(Panel footer)
        {
            if (report == null && !checking && !selfTest) RunChecks();
            int y = Header("Checking your PC", "Deployer needs a few things from Windows. Nothing is changed during this check.");

            // Summary banner
            string summary;
            IconKind icon;
            Color color, fill;
            if (report == null)
            {
                summary = "Checking your PC\u2026";
                icon = IconKind.Spinner;
                color = Theme.Accent;
                fill = Theme.SurfaceAlt;
            }
            else if (report.HasBlocking)
            {
                summary = "Some things need fixing before Deployer can be installed.";
                icon = IconKind.Cross;
                color = Theme.Danger;
                fill = Theme.DangerSoft;
            }
            else if (report.HasWarnings)
            {
                summary = "Your PC can run Deployer. Please read the notes below.";
                icon = IconKind.Warn;
                color = Theme.Warn;
                fill = Theme.WarnSoft;
            }
            else
            {
                summary = "Your PC is ready for Deployer.";
                icon = IconKind.Check;
                color = Theme.Success;
                fill = Theme.SuccessSoft;
            }
            Card banner = new Card(ui, fill, Color.Empty);
            int bh = ui.S(46);
            banner.Bounds = new Rectangle(ContentLeft, y, ContentWidth, bh);
            IconBadge bi = new IconBadge(ui, icon, color, false);
            bi.Bounds = new Rectangle(ui.S(14), (bh - ui.S(24)) / 2, ui.S(24), ui.S(24));
            banner.Controls.Add(bi);
            TextBlock bt = new TextBlock(ui, summary, ui.SemiBold(10f), Glyphs.Blend(color, Theme.Text, 0.5f));
            bt.SingleLine = true;
            bt.LayoutAt(ui.S(50), (bh - ui.SemiBold(10f).Height) / 2, ContentWidth - ui.S(170));
            banner.Controls.Add(bt);
            if (report != null)
            {
                FlatButton again = new FlatButton(ui, "Check again", ButtonStyle.Link);
                again.FontPoints = 9.5f;
                int aw = Ui.MeasureWidth(again.Text, ui.SemiBold(9.5f)) + ui.S(4);
                again.Bounds = new Rectangle(ContentWidth - aw - ui.S(16), (bh - ui.S(24)) / 2, aw, ui.S(24));
                again.Click += delegate { report = null; RunChecks(); Rebuild(); };
                banner.Controls.Add(again);
            }
            pageHost.Controls.Add(banner);
            y += bh + ui.S(16);

            if (report == null)
            {
                foreach (string id in SystemChecks.Ids)
                {
                    CheckRow row = new CheckRow(ui, CheckStatus.Running, SystemChecks.TitleFor(id), null, null, null);
                    y += row.LayoutAt(ContentLeft, y, ContentWidth) + ui.S(12);
                    pageHost.Controls.Add(row);
                }
            }
            else
            {
                foreach (CheckResult r in report.Items)
                {
                    CheckRow row = new CheckRow(ui, r.Status, r.Title, r.Detail, r.LinkText, r.LinkUrl);
                    y += row.LayoutAt(ContentLeft, y, ContentWidth) + ui.S(r.Detail != null ? 14 : 10);
                    pageHost.Controls.Add(row);
                }
            }
            AddBottomSpacer(y);
            StandardFooter(footer, "Next", true, delegate { if (report != null && !report.HasBlocking) GoTo(WizardPage.Docker); });
            nextButton.Enabled = report != null && !report.HasBlocking;
        }

        void AddBottomSpacer(int y)
        {
            Control spacer = new Control();
            spacer.Bounds = new Rectangle(ContentLeft, y, 1, ui.S(16));
            pageHost.Controls.Add(spacer);
        }

        void RunChecks()
        {
            checking = true;
            string dir = options.InstallDir;
            int port = options.Port;
            int installed = installedPort;
            ThreadPool.QueueUserWorkItem(delegate
            {
                SystemReport r;
                try
                {
                    r = SystemChecks.Run(dir, port, installed, true);
                }
                catch (Exception ex)
                {
                    r = new SystemReport();
                    r.Items.Add(new CheckResult("error", CheckStatus.Warn, "Some checks could not run", ex.Message));
                    r.Done = true;
                }
                try
                {
                    BeginInvoke((Action)delegate { ApplyReport(r); });
                }
                catch (InvalidOperationException)
                {
                }
            });
        }

        internal void ApplyReport(SystemReport r)
        {
            checking = false;
            report = r;
            if (!runtimeChosenByUser)
            {
                // Free Docker Engine in WSL2 by default, even when Docker Desktop is present: no licensing
                // conditions, and it keeps working after sleep/wake (Docker Desktop's socket files do not).
                options.Runtime = "wsl-engine";
            }
            if (!portEditedByUser && installedDir == null) options.Port = r.SuggestedPort;
            if (page == WizardPage.Checks) Rebuild();
        }

        // ------------------------------------------------------------------ Docker

        void BuildDocker(Panel footer)
        {
            int y = Header("How should Deployer run?",
                "Deployer runs its databases and web server in containers. The recommended choice suits almost everyone.");
            bool dockerWorks = report != null && report.DockerWorks;
            bool desktopInstalled = report != null && report.DockerDesktopInstalled;

            List<ChoiceCard> cards = new List<ChoiceCard>();
            ChoiceCard engine = new ChoiceCard(ui, "Free Docker Engine", "Recommended",
                "Open-source Docker Engine inside a private Linux environment (WSL2). Free for everyone, no account needed.");
            engine.Tag = "wsl-engine";
            cards.Add(engine);

            ChoiceCard desktop = new ChoiceCard(ui, "Docker Desktop", desktopInstalled ? "Installed" : null,
                "Free for personal use, education and small businesses; larger organisations need a paid Docker subscription \u2014 if that's you, sign in to Docker Desktop yourself after install.");
            desktop.BadgeColor = Theme.Accent;
            desktop.Tag = "docker-desktop";
            cards.Add(desktop);

            ChoiceCard existing = new ChoiceCard(ui, "Use my existing Docker", dockerWorks ? "Detected" : null,
                dockerWorks
                    ? "Docker " + report.DockerVersion + " is already running on this PC. Deployer will use it as it is."
                    : "Not available: no running Docker was found on this PC.");
            existing.BadgeColor = Theme.Accent;
            existing.Tag = "existing";
            existing.Enabled = dockerWorks;
            cards.Add(existing);

            if (installedDir == null && options.Runtime == "existing" && !dockerWorks) options.Runtime = "wsl-engine";
            if (installedDir != null)
            {
                y = Note(y, IconKind.Info, Theme.Accent, Theme.AccentSoft,
                    "This update keeps the choice made when Deployer was installed. To switch, uninstall first (keeping your data), then install again.");
            }
            foreach (ChoiceCard c in cards)
            {
                c.Checked = (string)c.Tag == options.Runtime;
                if (installedDir != null) c.Enabled = c.Checked;
                ChoiceCard captured = c;
                c.CheckedChanged += delegate
                {
                    if (!captured.Checked) return;
                    options.Runtime = (string)captured.Tag;
                    runtimeChosenByUser = true;
                    foreach (ChoiceCard other in cards) if (other != captured) other.Checked = false;
                };
                y += c.LayoutAt(ContentLeft, y, ContentWidth) + ui.S(12);
                pageHost.Controls.Add(c);
            }
            AddBottomSpacer(y);
            StandardFooter(footer, "Next", true, delegate { GoTo(WizardPage.Options); });
        }

        // ------------------------------------------------------------------ Options

        void BuildOptions(Panel footer)
        {
            int y = Header("Choose your options", null) - ui.S(6);
            Font labelFont = ui.SemiBold(10f);
            int inputH = ui.S(36);

            TextBlock dirLabel = new TextBlock(ui, "Install folder", labelFont, Theme.Text);
            y += dirLabel.LayoutAt(ContentLeft, y, ContentWidth) + ui.S(6);
            pageHost.Controls.Add(dirLabel);
            FlatButton browse = new FlatButton(ui, "Browse\u2026", ButtonStyle.Secondary);
            int bw = browse.PreferredWidth(ui.S(96));
            dirInput = new InputBox(ui, options.InstallDir);
            dirInput.Bounds = new Rectangle(ContentLeft, y, ContentWidth - bw - ui.S(10), inputH);
            dirInput.Box.ReadOnly = installedDir != null;
            dirInput.Box.TextChanged += delegate { options.InstallDir = dirInput.Box.Text.Trim(); ValidateOptions(); };
            pageHost.Controls.Add(dirInput);
            browse.Bounds = new Rectangle(ContentLeft + ContentWidth - bw, y, bw, inputH);
            browse.Enabled = installedDir == null;
            browse.Click += delegate { BrowseFolder(); };
            pageHost.Controls.Add(browse);
            y += inputH + ui.S(6);
            dirHint = new TextBlock(ui, "", ui.Font(9f), Theme.TextSubtle);
            dirHint.SingleLine = true;
            dirHint.LayoutAt(ContentLeft, y, ContentWidth);
            pageHost.Controls.Add(dirHint);
            y += dirHint.Height + ui.S(16);

            TextBlock portLabel = new TextBlock(ui, "Port", labelFont, Theme.Text);
            y += portLabel.LayoutAt(ContentLeft, y, ContentWidth) + ui.S(6);
            pageHost.Controls.Add(portLabel);
            portInput = new InputBox(ui, options.Port.ToString());
            portInput.Bounds = new Rectangle(ContentLeft, y, ui.S(96), inputH);
            portInput.Box.MaxLength = 5;
            portInput.Box.TextChanged += delegate
            {
                int p;
                portEditedByUser = true;
                options.Port = int.TryParse(portInput.Box.Text.Trim(), out p) ? p : -1;
                ValidateOptions();
            };
            pageHost.Controls.Add(portInput);
            portHint = new TextBlock(ui, "", ui.Font(9.5f), Theme.TextMuted);
            portHint.SingleLine = true;
            portHint.LayoutAt(ContentLeft + ui.S(110), y + (inputH - ui.Font(9.5f).Height) / 2, ContentWidth - ui.S(110));
            pageHost.Controls.Add(portHint);
            y += inputH + ui.S(14);

            Rule rule = new Rule(Theme.Border);
            rule.Bounds = new Rectangle(ContentLeft, y, ContentWidth, Math.Max(1, ui.S(1)));
            pageHost.Controls.Add(rule);
            y += ui.S(4);

            y = Toggle(y, "Let other devices on my network open Deployer",
                "Off keeps Deployer private to this PC. On allows phones and laptops on your home or office network (private networks only).",
                options.EnableLan, v => options.EnableLan = v);
            y = Toggle(y, "Keep this PC awake while plugged in",
                "Stops Windows from sleeping while the charger is connected, so your projects stay online. Useful for a PC that acts as a server.",
                options.KeepAwake, v => options.KeepAwake = v);
            y = Toggle(y, "Start Deployer when I sign in to Windows",
                "Runs Deployer in the background and shows its icon next to the clock.",
                options.Autostart, v => options.Autostart = v);
            y = Toggle(y, "Create a desktop shortcut", null, options.DesktopShortcut, v => options.DesktopShortcut = v);
            AddBottomSpacer(y);

            StandardFooter(footer, dryRun ? "Start test run" : (installedDir != null ? "Update" : "Install"), true, delegate
            {
                if (ValidateOptions()) StartInstall();
            });
            ValidateOptions();
        }

        int Toggle(int y, string title, string description, bool value, Action<bool> set)
        {
            ToggleRow row = new ToggleRow(ui, title, description, value);
            row.Changed += delegate { set(row.On); };
            y += row.LayoutAt(ContentLeft, y, ContentWidth);
            pageHost.Controls.Add(row);
            return y + ui.S(2);
        }

        void BrowseFolder()
        {
            using (FolderBrowserDialog dlg = new FolderBrowserDialog())
            {
                dlg.Description = "Choose where Deployer keeps its settings and databases. A \"Deployer\" folder is created inside the folder you pick.";
                dlg.ShowNewFolderButton = true;
                try
                {
                    string parent = Path.GetDirectoryName(options.InstallDir);
                    if (Directory.Exists(parent)) dlg.SelectedPath = parent;
                }
                catch (Exception)
                {
                }
                if (dlg.ShowDialog(this) != DialogResult.OK) return;
                string chosen = dlg.SelectedPath.TrimEnd('\\');
                if (!string.Equals(Path.GetFileName(chosen), "Deployer", StringComparison.OrdinalIgnoreCase))
                    chosen = Path.Combine(chosen.Length == 2 ? chosen + "\\" : chosen, "Deployer");
                dirInput.Box.Text = chosen;
            }
        }

        internal bool ValidateOptions()
        {
            string dirError = null;
            string dir = options.InstallDir ?? "";
            try
            {
                if (dir.Length < 4 || dir[1] != ':' || dir[2] != '\\' || !char.IsLetter(dir[0]))
                    dirError = "Use a full folder path on a local drive, like C:\\ProgramData\\Deployer.";
                else if (dir.IndexOfAny(Path.GetInvalidPathChars()) >= 0 || dir.IndexOfAny(new[] { '"', '*', '?', '<', '>', '|' }) >= 0 || dir.IndexOf(':', 2) >= 0)
                    dirError = "The folder name contains characters Windows doesn't allow.";
                else
                {
                    DriveInfo drive = new DriveInfo(dir.Substring(0, 3));
                    if (!drive.IsReady || drive.DriveType != DriveType.Fixed)
                        dirError = "Choose a folder on a local (non-removable) drive.";
                    else
                    {
                        double freeGb = drive.AvailableFreeSpace / 1073741824.0;
                        if (dirHint != null)
                            dirHint.Text = "Settings, databases and backups are stored here. " + Math.Round(freeGb) + " GB free on drive " + dir.Substring(0, 1).ToUpperInvariant();
                    }
                }
            }
            catch (Exception)
            {
                dirError = "That folder can't be used. Choose another one.";
            }
            if (dirHint != null)
            {
                if (dirError != null) dirHint.Text = dirError;
                dirHint.TextColor = dirError != null ? Theme.Danger : Theme.TextSubtle;
                dirHint.Invalidate();
            }
            if (dirInput != null) dirInput.Invalid = dirError != null;

            string portError = null;
            int port = options.Port;
            if (port < 1024 || port > 65535)
                portError = "Enter a number from 1024 to 65535.";
            else if (port != installedPort && !Ports.IsFree(port))
                portError = "Port " + port + " is already used by another program. Try " + Ports.SuggestFree(port) + ".";
            if (portHint != null)
            {
                portHint.Text = portError ?? "Deployer will open at http://localhost:" + port;
                portHint.TextColor = portError != null ? Theme.Danger : Theme.TextMuted;
                portHint.Invalidate();
            }
            if (portInput != null) portInput.Invalid = portError != null;
            bool ok = dirError == null && portError == null;
            if (nextButton != null && page == WizardPage.Options) nextButton.Enabled = ok;
            return ok;
        }

        // ------------------------------------------------------------------ Install

        void BuildInstall(Panel footer)
        {
            int y = Header(dryRun ? "Test run" : (installedDir != null ? "Updating Deployer" : "Installing Deployer"),
                dryRun ? "Every step is checked and explained, but nothing on this PC is changed."
                       : "This usually takes 10\u201330 minutes. You can keep using your PC.");

            Card card = new Card(ui, Theme.SurfaceAlt, Theme.Border);
            int pad = ui.S(20);
            int cw = ContentWidth;
            int cy = pad;
            stepLabel = new TextBlock(ui, stepText, ui.SemiBold(12f), Theme.Text);
            stepLabel.SingleLine = true;
            stepLabel.LayoutAt(pad, cy, cw - pad * 2 - ui.S(90));
            card.Controls.Add(stepLabel);
            stepCount = new TextBlock(ui, StepCountText(), ui.Font(9.5f), Theme.TextSubtle);
            stepCount.SingleLine = true;
            int scw = ui.S(90);
            stepCount.LayoutAt(cw - pad - scw, cy + (ui.SemiBold(12f).Height - ui.Font(9.5f).Height) / 2, scw);
            card.Controls.Add(stepCount);
            cy += ui.SemiBold(12f).Height + ui.S(12);
            progressLine = new ProgressLine(ui);
            progressLine.Bounds = new Rectangle(pad, cy, cw - pad * 2, ui.S(8));
            progressLine.Value = progress;
            card.Controls.Add(progressLine);
            cy += ui.S(8) + ui.S(10);
            transientLabel = new TextBlock(ui, transient, ui.Font(9f), Theme.TextSubtle);
            transientLabel.SingleLine = true;
            transientLabel.LayoutAt(pad, cy, cw - pad * 2);
            card.Controls.Add(transientLabel);
            cy += ui.Font(9f).Height + pad - ui.S(4);
            card.Bounds = new Rectangle(ContentLeft, y, cw, cy);
            pageHost.Controls.Add(card);
            y += cy + ui.S(14);

            FlatButton toggle = new FlatButton(ui, showDetails ? "Hide details" : "Show details", ButtonStyle.Link);
            toggle.FontPoints = 9.5f;
            toggle.Bounds = new Rectangle(ContentLeft, y, Ui.MeasureWidth(toggle.Text, ui.SemiBold(9.5f)) + ui.S(6), ui.S(24));
            toggle.Click += delegate { showDetails = !showDetails; Rebuild(); };
            pageHost.Controls.Add(toggle);
            y += ui.S(34);

            int available = pageHost.Height - y - ui.S(20);
            if (showDetails)
            {
                Card logCard = new Card(ui, Theme.SurfaceAlt, Theme.Border);
                logCard.Radius = 8;
                logCard.Bounds = new Rectangle(ContentLeft, y, cw, Math.Max(ui.S(120), available));
                logBox = new TextBox();
                logBox.Multiline = true;
                logBox.ReadOnly = true;
                logBox.ScrollBars = Program.SelfTestMode ? ScrollBars.None : ScrollBars.Vertical; // scroll bars do not print off-screen
                logBox.BorderStyle = BorderStyle.None;
                logBox.BackColor = Theme.SurfaceAlt;
                logBox.ForeColor = Theme.Text;
                logBox.Font = ui.Mono(8.5f);
                logBox.WordWrap = true;
                logBox.Bounds = new Rectangle(ui.S(12), ui.S(10), logCard.Width - ui.S(16), logCard.Height - ui.S(20));
                logBox.Text = log.ToString();
                logCard.Controls.Add(logBox);
                pageHost.Controls.Add(logCard);
                logBox.SelectionStart = logBox.TextLength;
                logBox.ScrollToCaret();
            }
            else
            {
                stepRows = new List<CheckRow>();
                int colGap = ui.S(24);
                int colW = (cw - colGap) / 2;
                int half = (totalSteps + 1) / 2;
                int rowY = y;
                for (int i = 0; i < totalSteps; i++)
                {
                    int col = i < half ? 0 : 1;
                    int ry = rowY + (i < half ? i : i - half) * ui.S(34);
                    CheckRow row = new CheckRow(ui, StepStatus(i + 1), stepNames[i], null, null, null);
                    row.SingleLine = true;
                    row.LayoutAt(ContentLeft + col * (colW + colGap), ry, colW);
                    stepRows.Add(row);
                    pageHost.Controls.Add(row);
                }
            }

            int left = ContentLeft - ui.S(12);
            FlatButton cancel = AddFooterButton(footer, "Cancel", ButtonStyle.Ghost, false, ref left, delegate { Close(); });
            cancel.Enabled = runner != null || selfTest;
            int right = footer.Width - ContentLeft;
            FlatButton wait = AddFooterButton(footer, dryRun ? "Testing\u2026" : "Installing\u2026", ButtonStyle.Primary, true, ref right, delegate { });
            wait.Enabled = false;
        }

        string StepCountText()
        {
            return step <= 0 ? "Starting" : "Step " + step + " of " + totalSteps;
        }

        CheckStatus StepStatus(int number)
        {
            if (number < step) return CheckStatus.Ok;
            if (number == step) return CheckStatus.Running;
            return CheckStatus.Pending;
        }

        void OnTick(object sender, EventArgs e)
        {
            if (page == WizardPage.Checks && report == null)
            {
                foreach (Control c in pageHost.Controls) if (c is CheckRow || c is Card) InvalidateTree(c);
            }
            if (page != WizardPage.Install || runner == null) return;
            double span = 1.0 / Math.Max(1, totalSteps);
            double baseP = Math.Max(0, step - 1) * span;
            double elapsed = (DateTime.Now - stepStarted).TotalSeconds;
            double creep = span * 0.85 * (1 - Math.Exp(-elapsed / 120.0));
            double target = Math.Min(0.99, baseP + creep);
            if (target > progress) progress = target;
            if (progressLine != null) progressLine.Value = progress;
            if (stepRows != null && step >= 1 && step <= stepRows.Count) stepRows[step - 1].Invalidate();
        }

        static void InvalidateTree(Control c)
        {
            c.Invalidate();
            foreach (Control child in c.Controls) InvalidateTree(child);
        }

        internal void StartInstall()
        {
            if (runner != null) return;
            step = 0;
            stepText = "Preparing";
            transient = "";
            progress = 0;
            errorMessage = "";
            sawDone = false;
            sawReboot = false;
            log.Length = 0;
            stepNames = (string[])DefaultStepNames.Clone();
            installStarted = DateTime.Now;
            stepStarted = DateTime.Now;
            page = WizardPage.Install;
            Rebuild();

            string dir = options.InstallDir.TrimEnd('\\');
            try
            {
                if (!dryRun)
                {
                    Directory.CreateDirectory(dir);
                    Integration.CopySelf(dir);
                    options.Save(Path.Combine(dir, AppInfo.OptionsFileName));
                }
                payloadRoot = Payload.Extract();
                List<string> args = new List<string>
                {
                    "-NonInteractive",
                    "-Runtime", options.Runtime,
                    "-InstallDir", dir,
                    "-Port", options.Port.ToString(),
                    "-Repo", AppInfo.Repo,
                    "-Ref", AppInfo.Ref,
                    "-LocalDeployDir", Path.Combine(payloadRoot, "deploy")
                };
                if (options.EnableLan) args.Add("-EnableLan");
                if (options.KeepAwake) args.Add("-PreventSleep");
                if (!options.Autostart) args.Add("-NoAutostart");
                if (resume) args.Add("-Resume");
                if (dryRun) args.Add("-DryRun");
                AppendLog("Deployer Setup " + AppInfo.Version + (dryRun ? " (test mode)" : "") + " - " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
                runner = new ScriptRunner();
                runner.OutputLine += line => SafeInvoke(() => OnInstallLine(line));
                runner.TransientLine += line => SafeInvoke(() => { transient = line.Trim(); if (transientLabel != null) transientLabel.Text = transient; });
                runner.Exited += code => SafeInvoke(() => OnInstallExited(code));
                runner.Start(Path.Combine(payloadRoot, @"installer\install.ps1"), args);
                Rebuild();
            }
            catch (Exception ex)
            {
                runner = null;
                errorMessage = "Setup couldn't start the installer: " + ex.Message;
                AppendLog(ex.ToString());
                page = WizardPage.Error;
                Rebuild();
            }
        }

        void SafeInvoke(Action a)
        {
            try
            {
                if (IsDisposed) return;
                BeginInvoke(a);
            }
            catch (InvalidOperationException)
            {
            }
        }

        internal void OnInstallLine(string line)
        {
            Marker m = Marker.Parse(line);
            if (m == null)
            {
                AppendLog(line);
                if (line.Trim().Length > 0 && !line.TrimStart().StartsWith("==>"))
                {
                    transient = line.Trim();
                    if (transientLabel != null) transientLabel.Text = transient;
                }
                return;
            }
            switch (m.Kind)
            {
                case MarkerKind.Step:
                    step = m.Step;
                    totalSteps = Math.Max(1, m.Total);
                    if (stepNames.Length != totalSteps)
                    {
                        string[] resized = new string[totalSteps];
                        for (int i = 0; i < totalSteps; i++) resized[i] = i < stepNames.Length ? stepNames[i] : "Step " + (i + 1);
                        stepNames = resized;
                    }
                    if (m.Step >= 1 && m.Step <= totalSteps) stepNames[m.Step - 1] = m.Text;
                    stepText = m.Text;
                    stepStarted = DateTime.Now;
                    progress = Math.Max(progress, (m.Step - 1) / (double)totalSteps);
                    transient = "";
                    if (stepLabel != null)
                    {
                        stepLabel.Text = stepText;
                        stepCount.Text = StepCountText();
                        transientLabel.Text = "";
                        if (stepRows != null && stepRows.Count == totalSteps)
                        {
                            for (int i = 0; i < stepRows.Count; i++)
                            {
                                stepRows[i].State = StepStatus(i + 1);
                                stepRows[i].Title = stepNames[i];
                                stepRows[i].Invalidate();
                            }
                        }
                        else if (!showDetails)
                        {
                            Rebuild();
                        }
                    }
                    break;
                case MarkerKind.RebootRequired:
                    sawReboot = true;
                    break;
                case MarkerKind.Done:
                    sawDone = true;
                    string url;
                    doneUrl = m.Values.TryGetValue("url", out url) ? url : "http://localhost:" + options.Port;
                    break;
                case MarkerKind.Error:
                    errorMessage = m.Text;
                    break;
                case MarkerKind.Check:
                    if (m.CheckState == "fail") AppendLog("[blocking] " + m.Text);
                    break;
            }
        }

        void AppendLog(string line)
        {
            if (log.Length > 400000) log.Remove(0, 100000);
            log.Append(line).Append("\r\n");
            if (logBox != null && !logBox.IsDisposed)
            {
                if (logBox.TextLength > 400000)
                {
                    logBox.Text = log.ToString();
                }
                else
                {
                    logBox.AppendText(line + "\r\n");
                }
            }
        }

        void OnInstallExited(int code)
        {
            bool cancelled = runner != null && runner.Cancelled;
            runner = null;
            string dir = options.InstallDir.TrimEnd('\\');
            AppendLog("Installer exited with code " + code + ".");
            if (cancelled)
            {
                errorMessage = "You stopped the installation. Run setup again whenever you're ready \u2014 it continues where it left off.";
                page = WizardPage.Error;
            }
            else if (sawReboot || code == 3010)
            {
                if (!dryRun)
                {
                    try
                    {
                        Integration.RegisterResume(dir);
                    }
                    catch (Exception ex)
                    {
                        AppendLog("Could not register resume after restart: " + ex.Message);
                    }
                }
                page = WizardPage.Reboot;
            }
            else if (sawDone && code == 0)
            {
                progress = 1;
                if (!dryRun) FinishIntegration(dir);
                page = WizardPage.Finish;
            }
            else
            {
                if (string.IsNullOrEmpty(errorMessage))
                    errorMessage = "The installer stopped unexpectedly (exit code " + code + ").";
                page = WizardPage.Error;
            }
            Payload.Cleanup(payloadRoot);
            payloadRoot = null;
            Rebuild();
            if (page == WizardPage.Finish || page == WizardPage.Error || page == WizardPage.Reboot)
            {
                try
                {
                    FlashWindow();
                }
                catch (Exception)
                {
                }
            }
        }

        void FlashWindow()
        {
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Activate();
        }

        void FinishIntegration(string dir)
        {
            try
            {
                Integration.CreateShortcuts(dir, options.Port, options.DesktopShortcut);
            }
            catch (Exception ex)
            {
                AppendLog("Shortcuts could not be created: " + ex.Message);
            }
            try
            {
                Integration.RegisterUninstallEntry(dir);
            }
            catch (Exception ex)
            {
                AppendLog("Apps & Features entry could not be created: " + ex.Message);
            }
            Integration.ClearResume();
            try
            {
                File.Delete(Path.Combine(dir, AppInfo.OptionsFileName));
            }
            catch (Exception)
            {
            }
        }

        // ------------------------------------------------------------------ Reboot / Error / Finish

        int BigIcon(int y, IconKind kind, Color color)
        {
            IconBadge b = new IconBadge(ui, kind, color, true);
            b.Bounds = new Rectangle(ContentLeft, y, ui.S(56), ui.S(56));
            pageHost.Controls.Add(b);
            return y + ui.S(56) + ui.S(18);
        }

        int Paragraph(int y, string text, Font font, Color color, int gapAfter)
        {
            TextBlock t = new TextBlock(ui, text, font, color);
            y += t.LayoutAt(ContentLeft, y, ContentWidth);
            pageHost.Controls.Add(t);
            return y + gapAfter;
        }

        void BuildReboot(Panel footer)
        {
            int y = BigIcon(ui.S(44), IconKind.Restart, Theme.Accent);
            y = Paragraph(y, "Restart needed", ui.SemiBold(19f), Theme.Text, ui.S(10));
            y = Paragraph(y, "Windows needs to restart to finish turning on the Linux environment (WSL) that Deployer uses.",
                ui.Font(11f), Theme.TextMuted, ui.S(14));
            y = Paragraph(y, "Deployer will continue automatically after you sign in \u2014 just approve the prompt that appears.",
                ui.Font(11f), Theme.TextMuted, ui.S(22));
            y = Note(y, IconKind.Info, Theme.Accent, Theme.AccentSoft, "Save your work in other apps before restarting.");

            int left = ContentLeft - ui.S(12);
            AddFooterButton(footer, "Later", ButtonStyle.Ghost, false, ref left, delegate
            {
                MessageDialog.Info(this, "Restart when you're ready", "Setup will continue after you restart Windows and sign in again.");
                Close();
            });
            int right = footer.Width - ContentLeft;
            FlatButton restart = AddFooterButton(footer, "Restart now", ButtonStyle.Primary, true, ref right, delegate { RestartNow(); });
            restart.Enabled = !dryRun;
            AcceptButton = restart;
        }

        void RestartNow()
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "shutdown.exe"),
                    "/r /t 5 /c \"Restarting to continue installing Deployer\"");
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                Process.Start(psi);
                allowClose = true;
                Close();
            }
            catch (Exception ex)
            {
                ErrorDialog.Show(this, "Couldn't restart Windows", "Please restart your PC from the Start menu. Setup continues after you sign in.", ex.ToString());
            }
        }

        void BuildError(Panel footer)
        {
            int y = BigIcon(ui.S(40), IconKind.Cross, Theme.Danger);
            y = Paragraph(y, "Setup couldn't finish", ui.SemiBold(19f), Theme.Text, ui.S(12));
            y = Note(y, IconKind.Warn, Theme.Danger, Theme.DangerSoft, string.IsNullOrEmpty(errorMessage) ? "Something went wrong." : errorMessage);
            y = Paragraph(y, "What you can try", ui.SemiBold(10.5f), Theme.Text, ui.S(6));
            foreach (string tip in new[]
            {
                "Check your internet connection, then click Try again \u2014 setup continues where it stopped.",
                "Restart your PC and run setup again.",
                "Look up the message in the troubleshooting guide, or share the details when asking for help."
            })
            {
                TextBlock bullet = new TextBlock(ui, "\u2022", ui.Font(10f), Theme.TextMuted);
                bullet.SingleLine = true;
                bullet.LayoutAt(ContentLeft + ui.S(2), y, ui.S(12));
                pageHost.Controls.Add(bullet);
                TextBlock tipText = new TextBlock(ui, tip, ui.Font(10f), Theme.TextMuted);
                y += tipText.LayoutAt(ContentLeft + ui.S(16), y, ContentWidth - ui.S(16)) + ui.S(3);
                pageHost.Controls.Add(tipText);
            }
            y += ui.S(10);
            LinkText help = new LinkText(ui, "Troubleshooting guide", AppInfo.TroubleshootingUrl);
            help.FontPoints = 10f;
            Size hs = help.Preferred();
            help.Bounds = new Rectangle(ContentLeft, y, hs.Width, hs.Height);
            pageHost.Controls.Add(help);
            if (!dryRun)
            {
                TextBlock logs = new TextBlock(ui, "Log files: " + Path.Combine(options.InstallDir, "logs"), ui.Font(9f), Theme.TextSubtle);
                logs.SingleLine = true;
                logs.LayoutAt(ContentLeft + hs.Width + ui.S(20), y + (hs.Height - ui.Font(9f).Height) / 2, ContentWidth - hs.Width - ui.S(20));
                pageHost.Controls.Add(logs);
            }
            y += hs.Height;
            AddBottomSpacer(y);

            int left = ContentLeft - ui.S(12);
            AddFooterButton(footer, "Close", ButtonStyle.Ghost, false, ref left, delegate { Close(); });
            int right = footer.Width - ContentLeft;
            FlatButton retry = AddFooterButton(footer, "Try again", ButtonStyle.Primary, true, ref right, delegate { rail.Failed = false; StartInstall(); });
            FlatButton copy = AddFooterButton(footer, "Copy details", ButtonStyle.Secondary, true, ref right, null);
            copy.Click += delegate
            {
                try
                {
                    Clipboard.SetText("Deployer Setup " + AppInfo.Version + " (" + Environment.OSVersion.VersionString + ")\r\nError: " + errorMessage + "\r\n\r\n" + log);
                    copy.Text = "Copied";
                }
                catch (Exception)
                {
                }
            };
            AcceptButton = retry;
        }

        void BuildFinish(Panel footer)
        {
            string url = string.IsNullOrEmpty(doneUrl) ? "http://localhost:" + options.Port : doneUrl;
            int y = BigIcon(ui.S(40), IconKind.Check, Theme.Success);
            y = Paragraph(y, dryRun ? "Test run complete" : "Deployer is ready", ui.SemiBold(19f), Theme.Text, ui.S(8));
            y = Paragraph(y, dryRun
                    ? "Every step checked out. Nothing was changed on this PC. Run DeployerSetup.exe without /dryrun to install."
                    : "Deployer is running on this PC at " + url + ".",
                ui.Font(11f), Theme.TextMuted, ui.S(20));

            FlatButton open = null;
            if (!dryRun)
            {
                open = new FlatButton(ui, "Open Deployer", ButtonStyle.Primary);
                open.FontPoints = 11f;
                open.Bounds = new Rectangle(ContentLeft, y, open.PreferredWidth(ui.S(200)), ui.S(46));
                open.Click += delegate { Shell.OpenUrl(url.TrimEnd('/') + "/setup"); };
                pageHost.Controls.Add(open);
                y += ui.S(46) + ui.S(28);
            }
            else
            {
                y += ui.S(6);
            }

            y = Paragraph(y, "Next steps", ui.SemiBold(10.5f), Theme.Text, ui.S(12));
            y = NextStep(y, 1, "Create your owner account", "Or restore everything from an export file made on another Deployer.");
            y = NextStep(y, 2, "Add Google or GitHub sign-in (optional)", "Use your own free OAuth apps \u2014 the setup page walks you through it.");
            y = NextStep(y, 3, "Already have a Deployer?", "Make this PC a host device for it from Settings \u2192 Devices in the dashboard.");
            y += ui.S(4);
            y = Paragraph(y, "Manage Deployer anytime from Deployer Control in the Start menu" + (options.Autostart ? " or next to the clock." : "."),
                ui.Font(9.5f), Theme.TextSubtle, 0);
            AddBottomSpacer(y);

            int right = footer.Width - ContentLeft;
            FlatButton finish = AddFooterButton(footer, "Finish", ButtonStyle.Secondary, true, ref right, delegate
            {
                allowClose = true;
                if (!dryRun && options.Autostart)
                {
                    try
                    {
                        Integration.StartTray(options.InstallDir.TrimEnd('\\'));
                    }
                    catch (Exception)
                    {
                    }
                }
                Close();
            });
            AcceptButton = open != null ? (IButtonControl)open : finish;
            finish.TabIndex = 10;
        }

        int NextStep(int y, int number, string title, string text)
        {
            int size = ui.S(26);
            NumberBadge nb = new NumberBadge(ui, number);
            nb.Bounds = new Rectangle(ContentLeft, y, size, size);
            pageHost.Controls.Add(nb);
            int tx = ContentLeft + size + ui.S(14);
            int tw = ContentWidth - size - ui.S(14);
            TextBlock t = new TextBlock(ui, title, ui.SemiBold(10f), Theme.Text);
            int h = t.LayoutAt(tx, y + ui.S(3), tw);
            pageHost.Controls.Add(t);
            TextBlock d = new TextBlock(ui, text, ui.Font(9.5f), Theme.TextMuted);
            h += ui.S(2) + d.LayoutAt(tx, y + ui.S(3) + h + ui.S(2), tw);
            pageHost.Controls.Add(d);
            return y + Math.Max(size, h + ui.S(3)) + ui.S(14);
        }

        // ------------------------------------------------------------------ closing

        bool allowClose;

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (runner != null && runner.IsRunning && !allowClose)
            {
                DialogResult r = MessageDialog.Ask(this, "Stop the installation?",
                    "Deployer isn't fully installed yet. You can run setup again later and it continues where it left off.",
                    IconKind.Warn, Theme.Warn, "Stop installation", ButtonStyle.Danger, "Keep installing");
                if (r != DialogResult.Yes)
                {
                    e.Cancel = true;
                    return;
                }
                runner.Cancel();
                e.Cancel = true;
                return;
            }
            if (page == WizardPage.Finish && !allowClose && !dryRun && options.Autostart && e.CloseReason == CloseReason.UserClosing)
            {
                try
                {
                    Integration.StartTray(options.InstallDir.TrimEnd('\\'));
                }
                catch (Exception)
                {
                }
            }
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            if (ticker != null) ticker.Stop();
            Payload.Cleanup(payloadRoot);
            base.OnFormClosed(e);
        }
    }

    class NumberBadge : PaintedControl
    {
        readonly int number;

        public NumberBadge(Ui ui, int number) : base(ui)
        {
            this.number = number;
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(0, 0, Width - 1, Height - 1);
            using (SolidBrush b = new SolidBrush(Theme.AccentSoft)) e.Graphics.FillEllipse(b, r);
            TextRenderer.DrawText(e.Graphics, number.ToString(), ui.SemiBold(9.5f), ClientRectangle, Theme.Accent,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.NoPadding);
        }
    }
}
