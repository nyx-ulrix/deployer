// Base form with per-monitor DPI handling, plus the themed message / error dialogs.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace DeployerSetup
{
    static class AppIcon
    {
        static Icon icon;

        public static Icon Get()
        {
            if (icon != null) return icon;
            try
            {
                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream("Deployer.ico"))
                {
                    if (s != null) icon = new Icon(s);
                }
            }
            catch (Exception)
            {
            }
            if (icon == null)
            {
                using (Bitmap bmp = Logo.Render(32)) icon = Icon.FromHandle(bmp.GetHicon());
            }
            return icon;
        }

        public static Icon Small()
        {
            try
            {
                return new Icon(Get(), SystemInformation.SmallIconSize);
            }
            catch (Exception)
            {
                return Get();
            }
        }
    }

    /// <summary>
    /// A form whose whole UI is rebuilt for its DPI: layout uses Ui.S() and pixel fonts, so the window
    /// looks the same at 100 %, 150 % or on a second monitor with a different scale.
    /// </summary>
    abstract class ThemedForm : Form
    {
        protected Ui ui;
        readonly float forcedScale;
        bool building;

        protected ThemedForm(float forcedScale)
        {
            this.forcedScale = forcedScale;
            AutoScaleMode = AutoScaleMode.None;
            BackColor = Theme.Surface;
            ForeColor = Theme.Text;
            StartPosition = FormStartPosition.Manual;
            Icon = AppIcon.Get();
            float f = forcedScale > 0 ? forcedScale : Ui.SystemFactor();
            ui = new Ui(f);
            Font = ui.Font(9.5f);
            KeyPreview = true;
        }

        protected bool IsForcedScale { get { return forcedScale > 0; } }

        protected override void SetVisibleCore(bool value)
        {
            // /selftest renders forms off-screen and must never put a window on the desktop.
            base.SetVisibleCore(Program.SelfTestMode ? false : value);
        }

        /// <summary>Called before the old controls are disposed, to save state held in them.</summary>
        protected virtual void BeforeRebuild()
        {
        }

        /// <summary>Creates all child controls for the current ui scale and sets ClientSize.</summary>
        protected abstract void BuildUi();

        public void Rebuild()
        {
            if (building) return;
            building = true;
            try
            {
                SuspendLayout();
                BeforeRebuild();
                List<Control> old = new List<Control>();
                foreach (Control c in Controls) old.Add(c);
                Controls.Clear();
                foreach (Control c in old) c.Dispose();
                Font = ui.Font(9.5f);
                BuildUi();
                ResumeLayout(true);
            }
            finally
            {
                building = false;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            if (!IsForcedScale)
            {
                float f = Ui.WindowFactor(Handle);
                if (Math.Abs(f - ui.Factor) > 0.01f)
                {
                    ui = new Ui(f);
                    Rebuild();
                }
            }
        }

        public void PlaceCentered(Form owner)
        {
            Rectangle area = owner != null && owner.Visible
                ? owner.Bounds
                : Screen.FromPoint(Cursor.Position).WorkingArea;
            Rectangle wa = Screen.FromRectangle(area).WorkingArea;
            int x = area.Left + (area.Width - Width) / 2;
            int y = area.Top + (area.Height - Height) / 2;
            x = Math.Max(wa.Left, Math.Min(x, wa.Right - Width));
            y = Math.Max(wa.Top, Math.Min(y, wa.Bottom - Height));
            Location = new Point(x, y);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == NativeMethods.WM_DPICHANGED && !IsForcedScale)
            {
                int dpi = (int)((long)m.WParam & 0xFFFF);
                NativeMethods.RECT r = (NativeMethods.RECT)Marshal.PtrToStructure(m.LParam, typeof(NativeMethods.RECT));
                ui = new Ui(dpi / 96f);
                Rebuild();
                // Keep the top-left where Windows suggests; the size follows our rebuilt layout.
                Location = new Point(r.Left, r.Top);
                m.Result = IntPtr.Zero;
                return;
            }
            base.WndProc(ref m);
        }

        /// <summary>Renders the client area (used by /selftest).</summary>
        public Bitmap RenderClient()
        {
            Bitmap bmp = new Bitmap(ClientSize.Width, ClientSize.Height, PixelFormat.Format24bppRgb);
            using (Graphics g = Graphics.FromImage(bmp)) g.Clear(BackColor);
            RenderChildren(this, bmp, Point.Empty, new Rectangle(Point.Empty, ClientSize));
            return bmp;
        }

        // The form is never shown during /selftest, so each control is printed individually
        // (back to front, clipped to its parent) instead of relying on child-window visibility.
        static void RenderChildren(Control parent, Bitmap bmp, Point origin, Rectangle clip)
        {
            List<Control> ordered = new List<Control>();
            foreach (Control c in parent.Controls) ordered.Add(c);
            ordered.Reverse();
            foreach (Control c in ordered)
            {
                if (c.Width <= 0 || c.Height <= 0) continue;
                Rectangle abs = new Rectangle(origin.X + c.Left, origin.Y + c.Top, c.Width, c.Height);
                Rectangle vis = Rectangle.Intersect(abs, clip);
                if (vis.Width <= 0 || vis.Height <= 0) continue;
                using (Bitmap part = new Bitmap(c.Width, c.Height, PixelFormat.Format24bppRgb))
                {
                    c.DrawToBitmap(part, new Rectangle(0, 0, c.Width, c.Height));
                    using (Graphics g = Graphics.FromImage(bmp))
                    {
                        g.DrawImage(part, vis, new Rectangle(vis.X - abs.X, vis.Y - abs.Y, vis.Width, vis.Height), GraphicsUnit.Pixel);
                    }
                }
                RenderChildren(c, bmp, abs.Location, vis);
            }
        }
    }

    /// <summary>Square checkbox with a label, e.g. "Also delete all databases and backups".</summary>
    class CheckOption : PaintedControl
    {
        bool isChecked;
        public string Description { get; set; }
        public Color CheckColor { get; set; }
        public event EventHandler Changed;

        public CheckOption(Ui ui, string text, string description) : base(ui)
        {
            Text = text;
            Description = description;
            CheckColor = Theme.Accent;
            Cursor = Cursors.Hand;
            TabStop = true;
            SetStyle(ControlStyles.Selectable, true);
            BackColor = Color.Transparent;
        }

        public bool Checked
        {
            get { return isChecked; }
            set
            {
                if (isChecked == value) return;
                isChecked = value;
                Invalidate();
                if (Changed != null) Changed(this, EventArgs.Empty);
            }
        }

        public int LayoutAt(int x, int y, int width)
        {
            int tw = width - ui.S(30);
            int h = Ui.MeasureHeight(Text, ui.SemiBold(10f), tw);
            if (!string.IsNullOrEmpty(Description)) h += ui.S(2) + Ui.MeasureHeight(Description, ui.Font(9.5f), tw);
            Bounds = new Rectangle(x, y, width, Math.Max(h, ui.S(20)));
            return Height;
        }

        protected override void OnClick(EventArgs e) { Focus(); Checked = !Checked; base.OnClick(e); }
        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space) Checked = !Checked;
            base.OnKeyUp(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            float box = ui.S(18);
            Font tf = ui.SemiBold(10f);
            RectangleF r = new RectangleF(ui.S(1), (tf.Height - box) / 2f + ui.S(1), box, box);
            using (GraphicsPath p = Logo.RoundedRect(r, ui.S(4)))
            {
                if (isChecked)
                {
                    using (SolidBrush b = new SolidBrush(CheckColor)) g.FillPath(b, p);
                    Glyphs.Draw(g, RectangleF.Inflate(r, ui.S(1), ui.S(1)), IconKind.Check, Color.White);
                }
                else
                {
                    using (SolidBrush b = new SolidBrush(Theme.Surface)) g.FillPath(b, p);
                    using (Pen pen = new Pen(Focused ? CheckColor : Theme.TextDisabled, Math.Max(1.5f, ui.Factor * 1.5f))) g.DrawPath(pen, p);
                }
            }
            int tw = Width - ui.S(30);
            int th = Ui.MeasureHeight(Text, tf, tw);
            TextRenderer.DrawText(g, Text, tf, new Rectangle(ui.S(30), 0, tw, th + ui.S(2)), Theme.Text, Ui.WrapFlags);
            if (!string.IsNullOrEmpty(Description))
            {
                Font df = ui.Font(9.5f);
                TextRenderer.DrawText(g, Description, df, new Rectangle(ui.S(30), th + ui.S(2), tw, Height - th), Theme.TextMuted, Ui.WrapFlags);
            }
        }
    }

    class DialogButton
    {
        public string Text;
        public ButtonStyle Style;
        public DialogResult Result;
        public Action OnClick;

        public DialogButton(string text, ButtonStyle style, DialogResult result)
        {
            Text = text;
            Style = style;
            Result = result;
        }
    }

    /// <summary>Themed replacement for MessageBox with an icon, wrapped text and optional checkbox.</summary>
    class MessageDialog : ThemedForm
    {
        readonly string title;
        readonly string message;
        readonly IconKind icon;
        readonly Color iconColor;
        readonly List<DialogButton> buttons;
        readonly string checkText;
        readonly string checkDescription;
        public bool CheckValue;
        public string LinkLabelText;
        public string LinkLabelUrl;
        const int DesignWidth = 500;

        public MessageDialog(string title, string message, IconKind icon, Color iconColor, List<DialogButton> buttons,
            string checkText, string checkDescription, float forcedScale)
            : base(forcedScale)
        {
            this.title = title;
            this.message = message;
            this.icon = icon;
            this.iconColor = iconColor;
            this.buttons = buttons;
            this.checkText = checkText;
            this.checkDescription = checkDescription;
            Text = title;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ShowInTaskbar = false;
            BuildUi();
        }

        protected override void BuildUi()
        {
            int w = ui.S(DesignWidth);
            int pad = ui.S(24);
            int left = ui.S(84);
            int tw = w - left - pad;

            IconBadge badge = new IconBadge(ui, icon, iconColor, true);
            badge.Bounds = new Rectangle(pad, pad, ui.S(44), ui.S(44));
            Controls.Add(badge);

            TextBlock t = new TextBlock(ui, title, ui.SemiBold(13f), Theme.Text);
            int y = pad + ui.S(2);
            y += t.LayoutAt(left, y, tw) + ui.S(8);
            Controls.Add(t);

            TextBlock m = new TextBlock(ui, message, ui.Font(10f), Theme.TextMuted);
            y += m.LayoutAt(left, y, tw);
            Controls.Add(m);

            if (!string.IsNullOrEmpty(LinkLabelText))
            {
                LinkText link = new LinkText(ui, LinkLabelText, LinkLabelUrl);
                link.FontPoints = 10f;
                Size ls = link.Preferred();
                y += ui.S(10);
                link.Bounds = new Rectangle(left, y, ls.Width, ls.Height);
                Controls.Add(link);
                y += ls.Height;
            }

            if (!string.IsNullOrEmpty(checkText))
            {
                y += ui.S(18);
                CheckOption opt = new CheckOption(ui, checkText, checkDescription);
                opt.CheckColor = iconColor == Theme.Danger ? Theme.Danger : Theme.Accent;
                opt.Checked = CheckValue;
                opt.Changed += delegate { CheckValue = opt.Checked; };
                y += opt.LayoutAt(left, y, tw);
                Controls.Add(opt);
            }
            y = Math.Max(y, pad + ui.S(44)) + pad;

            Panel footer = new Panel();
            footer.BackColor = Theme.SurfaceAlt;
            int fh = ui.S(68);
            footer.Bounds = new Rectangle(0, y, w, fh);
            Rule rule = new Rule(Theme.Border);
            rule.Bounds = new Rectangle(0, 0, w, Math.Max(1, ui.S(1)));
            footer.Controls.Add(rule);
            int bx = w - pad;
            int bh = ui.S(38);
            FlatButton firstPrimary = null;
            for (int i = buttons.Count - 1; i >= 0; i--)
            {
                DialogButton spec = buttons[i];
                FlatButton b = new FlatButton(ui, spec.Text, spec.Style);
                int bw = b.PreferredWidth(ui.S(96));
                bx -= bw;
                b.Bounds = new Rectangle(bx, (fh - bh) / 2, bw, bh);
                bx -= ui.S(10);
                DialogButton captured = spec;
                b.Click += delegate
                {
                    if (captured.OnClick != null)
                    {
                        captured.OnClick();
                        if (captured.Result == DialogResult.None) return;
                    }
                    DialogResult = captured.Result;
                    Close();
                };
                footer.Controls.Add(b);
                if (firstPrimary == null && (spec.Style == ButtonStyle.Primary || spec.Style == ButtonStyle.Danger)) firstPrimary = b;
                if (spec.Result == DialogResult.Cancel || spec.Result == DialogResult.No) CancelButton = b;
            }
            Controls.Add(footer);
            if (firstPrimary != null) AcceptButton = firstPrimary;
            ClientSize = new Size(w, y + fh);
        }

        public static DialogResult Ask(IWin32Window owner, string title, string message, IconKind icon, Color color,
            string yesText, ButtonStyle yesStyle, string noText)
        {
            // Never block or show UI during /selftest.
            if (Program.SelfTestMode) return DialogResult.Yes;
            List<DialogButton> buttons = new List<DialogButton>
            {
                new DialogButton(noText, ButtonStyle.Secondary, DialogResult.No),
                new DialogButton(yesText, yesStyle, DialogResult.Yes)
            };
            using (MessageDialog d = new MessageDialog(title, message, icon, color, buttons, null, null, 0))
            {
                d.PlaceCentered(owner as Form);
                return owner != null ? d.ShowDialog(owner) : d.ShowDialog();
            }
        }

        public static void Info(IWin32Window owner, string title, string message)
        {
            if (Program.SelfTestMode) return;
            List<DialogButton> buttons = new List<DialogButton> { new DialogButton("OK", ButtonStyle.Primary, DialogResult.OK) };
            using (MessageDialog d = new MessageDialog(title, message, IconKind.Info, Theme.Accent, buttons, null, null, 0))
            {
                d.PlaceCentered(owner as Form);
                if (owner != null) d.ShowDialog(owner); else d.ShowDialog();
            }
        }
    }

    static class ErrorDialog
    {
        public static MessageDialog Create(string title, string message, string details, float forcedScale)
        {
            List<DialogButton> buttons = new List<DialogButton>();
            DialogButton copy = new DialogButton("Copy details", ButtonStyle.Secondary, DialogResult.None);
            string all = title + "\r\n" + message + "\r\n\r\n" + (details ?? "") + "\r\n\r\nDeployer Setup " + AppInfo.Version +
                         " on " + Environment.OSVersion.VersionString;
            copy.OnClick = delegate
            {
                try { Clipboard.SetText(all); } catch (Exception) { }
            };
            buttons.Add(copy);
            buttons.Add(new DialogButton("Close", ButtonStyle.Primary, DialogResult.OK));
            MessageDialog d = new MessageDialog(title, message, IconKind.Cross, Theme.Danger, buttons, null, null, forcedScale);
            d.LinkLabelText = "Troubleshooting help";
            d.LinkLabelUrl = AppInfo.TroubleshootingUrl;
            d.Rebuild();
            return d;
        }

        public static void Show(IWin32Window owner, string title, string message, string details)
        {
            if (Program.SelfTestMode) return;
            using (MessageDialog d = Create(title, message, details, 0))
            {
                d.PlaceCentered(owner as Form);
                if (owner != null) d.ShowDialog(owner); else d.ShowDialog();
            }
        }
    }
}
