// Theme, DPI scaling and the small set of custom-painted controls used by every window.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace DeployerSetup
{
    static class Theme
    {
        public static readonly Color Accent = Hex(0x4F46E5);
        public static readonly Color AccentHover = Hex(0x4338CA);
        public static readonly Color AccentPressed = Hex(0x3730A3);
        public static readonly Color AccentSoft = Hex(0xEEF0FF);
        public static readonly Color AccentBorder = Hex(0xC7CCFB);
        public static readonly Color Text = Hex(0x111827);
        public static readonly Color TextMuted = Hex(0x4B5563);
        public static readonly Color TextSubtle = Hex(0x6B7280);
        public static readonly Color TextDisabled = Hex(0x9CA3AF);
        public static readonly Color Border = Hex(0xE5E7EB);
        public static readonly Color BorderStrong = Hex(0xD1D5DB);
        public static readonly Color Surface = Color.White;
        public static readonly Color SurfaceAlt = Hex(0xF9FAFB);
        public static readonly Color Rail = Hex(0xF5F6FA);
        public static readonly Color Hover = Hex(0xF3F4F6);
        public static readonly Color Success = Hex(0x16A34A);
        public static readonly Color SuccessSoft = Hex(0xE8F7EE);
        public static readonly Color SuccessText = Hex(0x166534);
        public static readonly Color Warn = Hex(0xD97706);
        public static readonly Color WarnSoft = Hex(0xFEF6E4);
        public static readonly Color WarnText = Hex(0x92400E);
        public static readonly Color Danger = Hex(0xDC2626);
        public static readonly Color DangerHover = Hex(0xB91C1C);
        public static readonly Color DangerSoft = Hex(0xFDECEC);
        public static readonly Color DangerText = Hex(0x991B1B);
        public static readonly Color Neutral = Hex(0x9CA3AF);
        public static readonly Color NeutralSoft = Hex(0xF3F4F6);

        public static Color Hex(int rgb)
        {
            return Color.FromArgb((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF);
        }
    }

    /// <summary>Converts 96-DPI design units to device pixels and caches pixel-sized fonts.</summary>
    class Ui
    {
        readonly Dictionary<string, Font> fonts = new Dictionary<string, Font>();
        public float Factor { get; private set; }

        public Ui(float factor)
        {
            Factor = factor <= 0 ? 1f : factor;
        }

        public int S(float value)
        {
            return (int)Math.Round(value * Factor);
        }

        public Font Font(float points)
        {
            return Font(points, FontStyle.Regular, false);
        }

        public Font Font(float points, FontStyle style)
        {
            return Font(points, style, false);
        }

        public Font SemiBold(float points)
        {
            return Font(points, FontStyle.Regular, true);
        }

        public Font Mono(float points)
        {
            string key = "mono|" + points;
            Font f;
            if (!fonts.TryGetValue(key, out f))
            {
                f = new Font("Consolas", points * 96f / 72f * Factor, FontStyle.Regular, GraphicsUnit.Pixel);
                fonts[key] = f;
            }
            return f;
        }

        public Font Font(float points, FontStyle style, bool semibold)
        {
            string key = points + "|" + (int)style + "|" + semibold;
            Font f;
            if (!fonts.TryGetValue(key, out f))
            {
                string family = semibold ? "Segoe UI Semibold" : "Segoe UI";
                f = new Font(family, points * 96f / 72f * Factor, style, GraphicsUnit.Pixel);
                if (semibold && f.Name != "Segoe UI Semibold")
                {
                    f.Dispose();
                    f = new Font("Segoe UI", points * 96f / 72f * Factor, style | FontStyle.Bold, GraphicsUnit.Pixel);
                }
                fonts[key] = f;
            }
            return f;
        }

        public static readonly TextFormatFlags WrapFlags =
            TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix;

        static Graphics bitmapGraphics;

        // On screen, text is measured and drawn with the screen DC. /selftest draws into bitmaps, whose
        // DC has slightly different glyph advances, so it measures with a bitmap DC to match.
        static IDeviceContext MeasureDc
        {
            get
            {
                if (!Program.SelfTestMode) return null;
                if (bitmapGraphics == null) bitmapGraphics = Graphics.FromImage(new Bitmap(4, 4, System.Drawing.Imaging.PixelFormat.Format24bppRgb));
                return bitmapGraphics;
            }
        }

        public static int MeasureHeight(string text, Font font, int width)
        {
            if (string.IsNullOrEmpty(text)) return 0;
            Size proposed = new Size(Math.Max(1, width), int.MaxValue);
            IDeviceContext dc = MeasureDc;
            Size sz = dc != null ? TextRenderer.MeasureText(dc, text, font, proposed, WrapFlags) : TextRenderer.MeasureText(text, font, proposed, WrapFlags);
            return sz.Height;
        }

        public static int MeasureWidth(string text, Font font)
        {
            if (string.IsNullOrEmpty(text)) return 0;
            Size proposed = new Size(int.MaxValue, int.MaxValue);
            TextFormatFlags flags = TextFormatFlags.SingleLine | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix;
            IDeviceContext dc = MeasureDc;
            return dc != null ? TextRenderer.MeasureText(dc, text, font, proposed, flags).Width : TextRenderer.MeasureText(text, font, proposed, flags).Width;
        }

        public static float SystemFactor()
        {
            try
            {
                return NativeMethods.GetDpiForSystem() / 96f;
            }
            catch (EntryPointNotFoundException)
            {
                using (Graphics g = Graphics.FromHwnd(IntPtr.Zero)) return g.DpiX / 96f;
            }
        }

        public static float WindowFactor(IntPtr hwnd)
        {
            try
            {
                uint dpi = NativeMethods.GetDpiForWindow(hwnd);
                if (dpi > 0) return dpi / 96f;
            }
            catch (EntryPointNotFoundException)
            {
            }
            return SystemFactor();
        }
    }

    static class NativeMethods
    {
        public const int WM_DPICHANGED = 0x02E0;

        [DllImport("user32.dll")]
        public static extern uint GetDpiForSystem();

        [DllImport("user32.dll")]
        public static extern uint GetDpiForWindow(IntPtr hwnd);

        [DllImport("kernel32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool IsProcessorFeaturePresent(uint feature);

        [StructLayout(LayoutKind.Sequential)]
        public struct MEMORYSTATUSEX
        {
            public uint dwLength;
            public uint dwMemoryLoad;
            public ulong ullTotalPhys;
            public ulong ullAvailPhys;
            public ulong ullTotalPageFile;
            public ulong ullAvailPageFile;
            public ulong ullTotalVirtual;
            public ulong ullAvailVirtual;
            public ulong ullAvailExtendedVirtual;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX buffer);

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT
        {
            public int Left, Top, Right, Bottom;
        }

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool MoveFileEx(string existing, string newName, int flags);
    }

    enum IconKind { None, Check, Warn, Cross, Info, Restart, Lock, Heart, Clock, User, Key, Devices, Dot, Spinner }

    static class Glyphs
    {
        /// <summary>Draws a filled circle with a white glyph (or a soft circle with a colored glyph).</summary>
        public static void Badge(Graphics g, RectangleF r, IconKind kind, Color color, bool soft)
        {
            SmoothingMode old = g.SmoothingMode;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Color fill = soft ? Blend(color, Color.White, 0.86f) : color;
            Color ink = soft ? color : Color.White;
            if (kind == IconKind.Spinner)
            {
                using (Pen track = new Pen(Theme.Border, Math.Max(1.5f, r.Width * 0.12f)))
                using (Pen arc = new Pen(color, Math.Max(1.5f, r.Width * 0.12f)))
                {
                    RectangleF rr = RectangleF.Inflate(r, -r.Width * 0.12f, -r.Height * 0.12f);
                    arc.StartCap = LineCap.Round;
                    arc.EndCap = LineCap.Round;
                    g.DrawEllipse(track, rr);
                    int angle = (int)(DateTime.Now.Ticks / TimeSpan.TicksPerMillisecond / 4 % 360);
                    g.DrawArc(arc, rr, angle, 100);
                }
                g.SmoothingMode = old;
                return;
            }
            using (SolidBrush b = new SolidBrush(fill)) g.FillEllipse(b, r);
            Draw(g, r, kind, ink);
            g.SmoothingMode = old;
        }

        public static Color Blend(Color a, Color b, float amountOfB)
        {
            return Color.FromArgb(
                (int)(a.R + (b.R - a.R) * amountOfB),
                (int)(a.G + (b.G - a.G) * amountOfB),
                (int)(a.B + (b.B - a.B) * amountOfB));
        }

        public static void Draw(Graphics g, RectangleF r, IconKind kind, Color ink)
        {
            float s = r.Width;
            float x = r.Left, y = r.Top;
            float w = Math.Max(1.4f, s * 0.1f);
            using (Pen pen = new Pen(ink, w))
            using (SolidBrush brush = new SolidBrush(ink))
            {
                pen.StartCap = LineCap.Round;
                pen.EndCap = LineCap.Round;
                pen.LineJoin = LineJoin.Round;
                switch (kind)
                {
                    case IconKind.Check:
                        g.DrawLines(pen, new PointF[] { P(x, y, s, 0.29f, 0.52f), P(x, y, s, 0.44f, 0.66f), P(x, y, s, 0.72f, 0.36f) });
                        break;
                    case IconKind.Cross:
                        g.DrawLine(pen, P(x, y, s, 0.35f, 0.35f), P(x, y, s, 0.65f, 0.65f));
                        g.DrawLine(pen, P(x, y, s, 0.65f, 0.35f), P(x, y, s, 0.35f, 0.65f));
                        break;
                    case IconKind.Warn:
                        g.DrawLine(pen, P(x, y, s, 0.5f, 0.28f), P(x, y, s, 0.5f, 0.56f));
                        g.FillEllipse(brush, x + s * 0.5f - w * 0.62f, y + s * 0.71f - w * 0.62f, w * 1.24f, w * 1.24f);
                        break;
                    case IconKind.Info:
                        g.DrawLine(pen, P(x, y, s, 0.5f, 0.46f), P(x, y, s, 0.5f, 0.72f));
                        g.FillEllipse(brush, x + s * 0.5f - w * 0.62f, y + s * 0.30f - w * 0.62f, w * 1.24f, w * 1.24f);
                        break;
                    case IconKind.Dot:
                        g.FillEllipse(brush, x + s * 0.34f, y + s * 0.34f, s * 0.32f, s * 0.32f);
                        break;
                    case IconKind.Restart:
                        {
                            // Circular arrow: arc with a gap at the top, arrowhead pointing clockwise into the gap.
                            float rad = s * 0.2f;
                            PointF c = P(x, y, s, 0.5f, 0.53f);
                            g.DrawArc(pen, c.X - rad, c.Y - rad, rad * 2, rad * 2, -50, 280);
                            double end = 230 * Math.PI / 180;
                            PointF tip0 = new PointF(c.X + rad * (float)Math.Cos(end), c.Y + rad * (float)Math.Sin(end));
                            PointF t = new PointF(-(float)Math.Sin(end), (float)Math.Cos(end));
                            PointF n = new PointF((float)Math.Cos(end), (float)Math.Sin(end));
                            float a = s * 0.11f;
                            PointF tip = new PointF(tip0.X + t.X * a * 0.9f, tip0.Y + t.Y * a * 0.9f);
                            g.DrawLines(pen, new PointF[]
                            {
                                new PointF(tip0.X + n.X * a - t.X * a * 0.2f, tip0.Y + n.Y * a - t.Y * a * 0.2f),
                                tip,
                                new PointF(tip0.X - n.X * a - t.X * a * 0.2f, tip0.Y - n.Y * a - t.Y * a * 0.2f)
                            });
                            break;
                        }
                    case IconKind.Lock:
                        g.DrawArc(pen, x + s * 0.36f, y + s * 0.24f, s * 0.28f, s * 0.30f, 180, 180);
                        g.DrawLine(pen, P(x, y, s, 0.36f, 0.39f), P(x, y, s, 0.36f, 0.46f));
                        g.DrawLine(pen, P(x, y, s, 0.64f, 0.39f), P(x, y, s, 0.64f, 0.46f));
                        using (GraphicsPath body = Logo.RoundedRect(new RectangleF(x + s * 0.28f, y + s * 0.46f, s * 0.44f, s * 0.30f), s * 0.05f))
                            g.FillPath(brush, body);
                        break;
                    case IconKind.Heart:
                        using (GraphicsPath heart = new GraphicsPath())
                        {
                            heart.AddBezier(P(x, y, s, 0.5f, 0.74f), P(x, y, s, 0.18f, 0.52f), P(x, y, s, 0.24f, 0.24f), P(x, y, s, 0.5f, 0.38f));
                            heart.AddBezier(P(x, y, s, 0.5f, 0.38f), P(x, y, s, 0.76f, 0.24f), P(x, y, s, 0.82f, 0.52f), P(x, y, s, 0.5f, 0.74f));
                            g.FillPath(brush, heart);
                        }
                        break;
                    case IconKind.Clock:
                        using (Pen thin = new Pen(ink, Math.Max(1.4f, s * 0.07f)))
                        {
                            thin.StartCap = LineCap.Round;
                            thin.EndCap = LineCap.Round;
                            thin.LineJoin = LineJoin.Round;
                            g.DrawEllipse(thin, x + s * 0.27f, y + s * 0.27f, s * 0.46f, s * 0.46f);
                            g.DrawLines(thin, new PointF[] { P(x, y, s, 0.5f, 0.37f), P(x, y, s, 0.5f, 0.5f), P(x, y, s, 0.59f, 0.56f) });
                        }
                        break;
                    case IconKind.User:
                        g.DrawEllipse(pen, x + s * 0.39f, y + s * 0.25f, s * 0.22f, s * 0.22f);
                        g.DrawArc(pen, x + s * 0.28f, y + s * 0.53f, s * 0.44f, s * 0.36f, 180, 180);
                        break;
                    case IconKind.Key:
                        g.DrawEllipse(pen, x + s * 0.24f, y + s * 0.38f, s * 0.24f, s * 0.24f);
                        g.DrawLine(pen, P(x, y, s, 0.48f, 0.5f), P(x, y, s, 0.76f, 0.5f));
                        g.DrawLine(pen, P(x, y, s, 0.68f, 0.5f), P(x, y, s, 0.68f, 0.62f));
                        break;
                    case IconKind.Devices:
                        using (GraphicsPath screen = Logo.RoundedRect(new RectangleF(x + s * 0.24f, y + s * 0.30f, s * 0.52f, s * 0.34f), s * 0.04f))
                            g.DrawPath(pen, screen);
                        g.DrawLine(pen, P(x, y, s, 0.40f, 0.74f), P(x, y, s, 0.60f, 0.74f));
                        break;
                }
            }
        }

        static PointF P(float x, float y, float s, float fx, float fy)
        {
            return new PointF(x + s * fx, y + s * fy);
        }
    }

    /// <summary>Base for custom-painted controls: double buffered, transparent-friendly, scaled.</summary>
    class PaintedControl : Control
    {
        protected Ui ui;

        public PaintedControl(Ui ui)
        {
            this.ui = ui;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint |
                     ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
            BackColor = Theme.Surface;
        }

        protected Color ParentBack()
        {
            Control p = Parent;
            while (p != null && p.BackColor.A < 255) p = p.Parent;
            return p != null ? p.BackColor : Theme.Surface;
        }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            using (SolidBrush b = new SolidBrush(BackColor.A < 255 ? ParentBack() : BackColor))
                e.Graphics.FillRectangle(b, ClientRectangle);
        }
    }

    enum ButtonStyle { Primary, Secondary, Ghost, Danger, DangerGhost, Link }

    class FlatButton : PaintedControl, IButtonControl
    {
        bool hover, pressed;
        public ButtonStyle Style { get; set; }
        public DialogResult DialogResult { get; set; }
        public float FontPoints { get; set; }

        public FlatButton(Ui ui, string text, ButtonStyle style) : base(ui)
        {
            Text = text;
            Style = style;
            FontPoints = 10f;
            SetStyle(ControlStyles.Selectable | ControlStyles.StandardClick, true);
            TabStop = true;
            Cursor = Cursors.Hand;
            BackColor = Color.Transparent;
        }

        public int PreferredWidth(int min)
        {
            return Math.Max(min, Ui.MeasureWidth(Text, ui.SemiBold(FontPoints)) + ui.S(36));
        }

        public void NotifyDefault(bool value) { }

        public void PerformClick()
        {
            if (CanSelect || Enabled) OnClick(EventArgs.Empty);
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; pressed = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { if (e.Button == MouseButtons.Left) { pressed = true; Invalidate(); } base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { pressed = false; Invalidate(); base.OnMouseUp(e); }
        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }
        protected override void OnEnabledChanged(EventArgs e) { Cursor = Enabled ? Cursors.Hand : Cursors.Default; Invalidate(); base.OnEnabledChanged(e); }
        protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter) PerformClick();
            base.OnKeyUp(e);
        }

        protected override bool IsInputKey(Keys keyData)
        {
            return keyData == Keys.Enter || keyData == Keys.Space || base.IsInputKey(keyData);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f);
            Color fill = Color.Empty, border = Color.Empty, text = Theme.Text;
            bool on = Enabled;
            switch (Style)
            {
                case ButtonStyle.Primary:
                    fill = !on ? Theme.BorderStrong : pressed ? Theme.AccentPressed : hover ? Theme.AccentHover : Theme.Accent;
                    text = Color.White;
                    break;
                case ButtonStyle.Danger:
                    fill = !on ? Theme.BorderStrong : pressed || hover ? Theme.DangerHover : Theme.Danger;
                    text = Color.White;
                    break;
                case ButtonStyle.Secondary:
                    fill = pressed ? Theme.Border : hover ? Theme.Hover : Theme.Surface;
                    border = Theme.BorderStrong;
                    text = on ? Theme.Text : Theme.TextDisabled;
                    break;
                case ButtonStyle.Ghost:
                    fill = pressed ? Theme.Border : hover ? Theme.Hover : Color.Empty;
                    text = on ? Theme.TextMuted : Theme.TextDisabled;
                    break;
                case ButtonStyle.DangerGhost:
                    fill = pressed ? Theme.DangerSoft : hover ? Theme.DangerSoft : Color.Empty;
                    text = on ? Theme.Danger : Theme.TextDisabled;
                    break;
                case ButtonStyle.Link:
                    text = on ? (hover ? Theme.AccentHover : Theme.Accent) : Theme.TextDisabled;
                    break;
            }
            float radius = ui.S(8);
            using (GraphicsPath path = Logo.RoundedRect(r, radius))
            {
                if (fill != Color.Empty) using (SolidBrush b = new SolidBrush(fill)) g.FillPath(b, path);
                if (border != Color.Empty) using (Pen p = new Pen(border, Math.Max(1f, ui.Factor))) g.DrawPath(p, path);
            }
            if (Focused && ShowFocusCues && Style != ButtonStyle.Link)
            {
                RectangleF fr = RectangleF.Inflate(r, -ui.S(3), -ui.S(3));
                using (GraphicsPath fp = Logo.RoundedRect(fr, radius - ui.S(2)))
                using (Pen p = new Pen(Style == ButtonStyle.Primary || Style == ButtonStyle.Danger ? Color.White : Theme.Accent, Math.Max(1f, ui.Factor)))
                {
                    p.DashStyle = DashStyle.Dot;
                    g.DrawPath(p, fp);
                }
            }
            Font font = Style == ButtonStyle.Link && hover ? ui.Font(FontPoints, FontStyle.Underline, true) : ui.SemiBold(FontPoints);
            TextFormatFlags flags = TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine |
                                    TextFormatFlags.NoPrefix | TextFormatFlags.EndEllipsis;
            if (Style == ButtonStyle.Link) flags = TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix | TextFormatFlags.NoPadding;
            TextRenderer.DrawText(g, Text, font, ClientRectangle, text, flags);
        }
    }

    /// <summary>Wrapped text with an exact measured height.</summary>
    class TextBlock : PaintedControl
    {
        public Font TextFont { get; set; }
        public Color TextColor { get; set; }
        public bool SingleLine { get; set; }
        public bool RightAlign { get; set; }

        public TextBlock(Ui ui, string text, Font font, Color color) : base(ui)
        {
            Text = text;
            TextFont = font;
            TextColor = color;
            BackColor = Color.Transparent;
        }

        public int LayoutAt(int x, int y, int width)
        {
            int h = SingleLine ? TextFont.Height : Ui.MeasureHeight(Text, TextFont, width);
            Bounds = new Rectangle(x, y, width, Math.Max(h, 1));
            return h;
        }

        protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            TextFormatFlags flags = SingleLine
                ? TextFormatFlags.SingleLine | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix | TextFormatFlags.EndEllipsis
                : Ui.WrapFlags;
            if (RightAlign) flags |= TextFormatFlags.Right;
            TextRenderer.DrawText(e.Graphics, Text, TextFont, ClientRectangle, TextColor, flags);
        }
    }

    /// <summary>A clickable text link that opens a URL (unelevated, through explorer.exe) or runs an action.</summary>
    class LinkText : PaintedControl
    {
        bool hover;
        public string Url { get; set; }
        public float FontPoints { get; set; }
        public Color LinkColor { get; set; }

        public LinkText(Ui ui, string text, string url) : base(ui)
        {
            Text = text;
            Url = url;
            FontPoints = 9.5f;
            LinkColor = Theme.Accent;
            Cursor = Cursors.Hand;
            BackColor = Color.Transparent;
            SetStyle(ControlStyles.Selectable, true);
            TabStop = true;
        }

        public Size Preferred()
        {
            Font f = ui.SemiBold(FontPoints);
            return new Size(Ui.MeasureWidth(Text, f) + ui.S(2), f.Height + ui.S(2));
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }

        protected override void OnClick(EventArgs e)
        {
            if (!string.IsNullOrEmpty(Url)) Shell.OpenUrl(Url);
            base.OnClick(e);
        }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter || e.KeyCode == Keys.Space) OnClick(EventArgs.Empty);
            base.OnKeyUp(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Font f = hover ? ui.Font(FontPoints, FontStyle.Underline, true) : ui.SemiBold(FontPoints);
            TextRenderer.DrawText(e.Graphics, Text, f, ClientRectangle, hover ? Theme.AccentHover : LinkColor,
                TextFormatFlags.SingleLine | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix | TextFormatFlags.VerticalCenter);
            if (Focused && ShowFocusCues) ControlPaint.DrawFocusRectangle(e.Graphics, ClientRectangle);
        }
    }

    /// <summary>Rounded card background (optionally tinted) that hosts child controls.</summary>
    class Card : Panel
    {
        readonly Ui ui;
        Color fill;
        public Color BorderColor { get; set; }

        /// <summary>Card color; also the BackColor that transparent children paint behind them.</summary>
        public Color Fill
        {
            get { return fill; }
            set { fill = value; BackColor = value; Invalidate(true); }
        }
        public float Radius { get; set; }

        public Card(Ui ui, Color fill, Color border)
        {
            this.ui = ui;
            Fill = fill;
            BorderColor = border;
            Radius = 10;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
            BackColor = fill;
        }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            Control p = Parent;
            Color back = p != null ? p.BackColor : Theme.Surface;
            using (SolidBrush b = new SolidBrush(back)) e.Graphics.FillRectangle(b, ClientRectangle);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f);
            using (GraphicsPath path = Logo.RoundedRect(r, ui.S(Radius)))
            {
                using (SolidBrush b = new SolidBrush(Fill)) e.Graphics.FillPath(b, path);
                if (BorderColor != Color.Empty) using (Pen pen = new Pen(BorderColor, Math.Max(1f, ui.Factor))) e.Graphics.DrawPath(pen, path);
            }
        }
    }

    /// <summary>Round icon badge (check, warning, restart...).</summary>
    class IconBadge : PaintedControl
    {
        public IconKind Kind { get; set; }
        public Color Color { get; set; }
        public bool Soft { get; set; }

        public IconBadge(Ui ui, IconKind kind, Color color, bool soft) : base(ui)
        {
            Kind = kind;
            Color = color;
            Soft = soft;
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            float inset = Math.Max(1f, ui.Factor);
            Glyphs.Badge(e.Graphics, new RectangleF(inset, inset, Width - inset * 2 - 1, Height - inset * 2 - 1), Kind, Color, Soft);
        }
    }

    class LogoMark : PaintedControl
    {
        public LogoMark(Ui ui) : base(ui)
        {
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            Logo.Draw(e.Graphics, new RectangleF(0, 0, Width - 1, Height - 1));
        }
    }

    enum CheckStatus { Pending, Running, Ok, Warn, Fail }

    /// <summary>One line of the system check: status icon, title, optional explanation and link.</summary>
    class CheckRow : PaintedControl
    {
        public CheckStatus State { get; set; }
        public string Title { get; set; }
        public string Detail { get; set; }
        /// <summary>One line with an ellipsis (used for the fixed grid of install steps).</summary>
        public bool SingleLine { get; set; }
        LinkText link;

        public CheckRow(Ui ui, CheckStatus state, string title, string detail, string linkText, string linkUrl) : base(ui)
        {
            State = state;
            Title = title;
            Detail = detail;
            BackColor = Color.Transparent;
            if (!string.IsNullOrEmpty(linkText))
            {
                link = new LinkText(ui, linkText, linkUrl);
                link.FontPoints = 9f;
                Controls.Add(link);
            }
        }

        int TextLeft { get { return ui.S(34); } }

        public int LayoutAt(int x, int y, int width)
        {
            int textWidth = width - TextLeft;
            int h = SingleLine ? ui.SemiBold(10f).Height : Ui.MeasureHeight(Title, ui.SemiBold(10f), textWidth);
            if (!string.IsNullOrEmpty(Detail)) h += ui.S(2) + Ui.MeasureHeight(Detail, ui.Font(9.5f), textWidth);
            if (link != null)
            {
                Size ls = link.Preferred();
                link.Bounds = new Rectangle(TextLeft, h + ui.S(3), ls.Width, ls.Height);
                h += ui.S(3) + ls.Height;
            }
            h = Math.Max(h, ui.S(22));
            Bounds = new Rectangle(x, y, width, h);
            return h;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            RectangleF icon = new RectangleF(0, ui.S(1), ui.S(21), ui.S(21));
            switch (State)
            {
                case CheckStatus.Ok: Glyphs.Badge(g, icon, IconKind.Check, Theme.Success, false); break;
                case CheckStatus.Warn: Glyphs.Badge(g, icon, IconKind.Warn, Theme.Warn, false); break;
                case CheckStatus.Fail: Glyphs.Badge(g, icon, IconKind.Cross, Theme.Danger, false); break;
                case CheckStatus.Running: Glyphs.Badge(g, icon, IconKind.Spinner, Theme.Accent, false); break;
                default:
                    using (Pen p = new Pen(Theme.BorderStrong, Math.Max(1.5f, ui.Factor * 1.5f)))
                    {
                        g.SmoothingMode = SmoothingMode.AntiAlias;
                        g.DrawEllipse(p, RectangleF.Inflate(icon, -ui.S(2), -ui.S(2)));
                    }
                    break;
            }
            int textWidth = Width - TextLeft;
            Font tf = ui.SemiBold(10f);
            int th = SingleLine ? tf.Height : Ui.MeasureHeight(Title, tf, textWidth);
            TextRenderer.DrawText(g, Title, tf, new Rectangle(TextLeft, 0, textWidth, th + ui.S(2)),
                State == CheckStatus.Pending ? Theme.TextSubtle : Theme.Text,
                SingleLine ? TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix : Ui.WrapFlags);
            if (!string.IsNullOrEmpty(Detail))
            {
                Font df = ui.Font(9.5f);
                int dh = Ui.MeasureHeight(Detail, df, textWidth);
                TextRenderer.DrawText(g, Detail, df, new Rectangle(TextLeft, th + ui.S(2), textWidth, dh + ui.S(2)), Theme.TextMuted, Ui.WrapFlags);
            }
        }
    }

    /// <summary>Selectable card with a radio circle, title, optional badge and description.</summary>
    class ChoiceCard : PaintedControl
    {
        bool hover;
        bool isChecked;
        public string Title { get; set; }
        public string Badge { get; set; }
        public Color BadgeColor { get; set; }
        public string Description { get; set; }
        public event EventHandler CheckedChanged;

        public ChoiceCard(Ui ui, string title, string badge, string description) : base(ui)
        {
            Title = title;
            Badge = badge;
            BadgeColor = Theme.Success;
            Description = description;
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
                if (CheckedChanged != null) CheckedChanged(this, EventArgs.Empty);
            }
        }

        int Pad { get { return ui.S(16); } }
        int TextLeft { get { return ui.S(50); } }

        public int LayoutAt(int x, int y, int width)
        {
            int tw = width - TextLeft - Pad;
            int h = Pad + ui.SemiBold(10.5f).Height + ui.S(4) + Ui.MeasureHeight(Description, ui.Font(9.5f), tw) + Pad;
            Bounds = new Rectangle(x, y, width, h);
            return h;
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnClick(EventArgs e) { if (Enabled) { Focus(); Checked = true; } base.OnClick(e); }
        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }
        protected override void OnEnabledChanged(EventArgs e) { Cursor = Enabled ? Cursors.Hand : Cursors.Default; Invalidate(); base.OnEnabledChanged(e); }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space && Enabled) Checked = true;
            base.OnKeyUp(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(ui.Factor * 0.75f, ui.Factor * 0.75f, Width - ui.Factor * 1.5f - 1, Height - ui.Factor * 1.5f - 1);
            Color fill = !Enabled ? Theme.SurfaceAlt : isChecked ? Theme.AccentSoft : hover ? Theme.SurfaceAlt : Theme.Surface;
            Color border = !Enabled ? Theme.Border : isChecked ? Theme.Accent : hover ? Theme.BorderStrong : Theme.Border;
            float bw = isChecked ? Math.Max(1.5f, ui.Factor * 1.5f) : Math.Max(1f, ui.Factor);
            using (GraphicsPath path = Logo.RoundedRect(r, ui.S(10)))
            {
                using (SolidBrush b = new SolidBrush(fill)) g.FillPath(b, path);
                using (Pen p = new Pen(border, bw)) g.DrawPath(p, path);
            }
            if (Focused && ShowFocusCues)
            {
                using (GraphicsPath fp = Logo.RoundedRect(RectangleF.Inflate(r, -ui.S(4), -ui.S(4)), ui.S(7)))
                using (Pen p = new Pen(Theme.Accent, Math.Max(1f, ui.Factor)))
                {
                    p.DashStyle = DashStyle.Dot;
                    g.DrawPath(p, fp);
                }
            }

            float rs = ui.S(18);
            Font tf = ui.SemiBold(10.5f);
            RectangleF radio = new RectangleF(Pad, Pad + (tf.Height - rs) / 2f, rs, rs);
            using (Pen p = new Pen(!Enabled ? Theme.BorderStrong : isChecked ? Theme.Accent : Theme.TextDisabled, Math.Max(1.5f, ui.Factor * 1.5f)))
                g.DrawEllipse(p, radio);
            if (isChecked)
            {
                using (SolidBrush b = new SolidBrush(Theme.Accent))
                    g.FillEllipse(b, RectangleF.Inflate(radio, -rs * 0.26f, -rs * 0.26f));
            }

            Color titleColor = Enabled ? Theme.Text : Theme.TextDisabled;
            int tw = Width - TextLeft - Pad;
            TextRenderer.DrawText(g, Title, tf, new Point(TextLeft, Pad), titleColor, TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix);
            if (!string.IsNullOrEmpty(Badge))
            {
                Font bf = ui.SemiBold(8.5f);
                int bx = TextLeft + Ui.MeasureWidth(Title, tf) + ui.S(10);
                int bwid = Ui.MeasureWidth(Badge, bf) + ui.S(16);
                int bh = bf.Height + ui.S(4);
                RectangleF br = new RectangleF(bx, Pad + (tf.Height - bh) / 2f, bwid, bh);
                Color bc = Enabled ? BadgeColor : Theme.TextDisabled;
                using (GraphicsPath bp = Logo.RoundedRect(br, bh / 2f))
                using (SolidBrush b = new SolidBrush(Glyphs.Blend(bc, Color.White, 0.86f)))
                    g.FillPath(b, bp);
                TextRenderer.DrawText(g, Badge, bf, Rectangle.Round(br), Glyphs.Blend(bc, Color.Black, 0.25f),
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.NoPadding);
            }
            Font df = ui.Font(9.5f);
            int dy = Pad + tf.Height + ui.S(4);
            TextRenderer.DrawText(g, Description, df, new Rectangle(TextLeft, dy, tw, Height - dy), Enabled ? Theme.TextMuted : Theme.TextDisabled, Ui.WrapFlags);
        }
    }

    /// <summary>Title + description with an on/off switch on the right.</summary>
    class ToggleRow : PaintedControl
    {
        bool isOn;
        bool hover;
        public string Title { get; set; }
        public string Description { get; set; }
        public event EventHandler Changed;

        public ToggleRow(Ui ui, string title, string description, bool on) : base(ui)
        {
            Title = title;
            Description = description;
            isOn = on;
            Cursor = Cursors.Hand;
            TabStop = true;
            SetStyle(ControlStyles.Selectable, true);
            BackColor = Color.Transparent;
        }

        public bool On
        {
            get { return isOn; }
            set
            {
                if (isOn == value) return;
                isOn = value;
                Invalidate();
                if (Changed != null) Changed(this, EventArgs.Empty);
            }
        }

        int SwitchWidth { get { return ui.S(40); } }

        public int LayoutAt(int x, int y, int width)
        {
            int tw = width - SwitchWidth - ui.S(24);
            int h = ui.S(10) + Ui.MeasureHeight(Title, ui.SemiBold(10f), tw);
            if (!string.IsNullOrEmpty(Description)) h += ui.S(2) + Ui.MeasureHeight(Description, ui.Font(9.5f), tw);
            h += ui.S(10);
            Bounds = new Rectangle(x, y, width, h);
            return h;
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnClick(EventArgs e) { if (Enabled) { Focus(); On = !On; } base.OnClick(e); }
        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space && Enabled) On = !On;
            base.OnKeyUp(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            int tw = Width - SwitchWidth - ui.S(24);
            Font tf = ui.SemiBold(10f);
            int th = Ui.MeasureHeight(Title, tf, tw);
            TextRenderer.DrawText(g, Title, tf, new Rectangle(0, ui.S(10), tw, th + ui.S(2)), Enabled ? Theme.Text : Theme.TextDisabled, Ui.WrapFlags);
            if (!string.IsNullOrEmpty(Description))
            {
                Font df = ui.Font(9.5f);
                int dh = Ui.MeasureHeight(Description, df, tw);
                TextRenderer.DrawText(g, Description, df, new Rectangle(0, ui.S(12) + th, tw, dh + ui.S(2)), Theme.TextMuted, Ui.WrapFlags);
            }

            float sw = SwitchWidth, sh = ui.S(22);
            RectangleF track = new RectangleF(Width - sw - ui.S(2), ui.S(10) + (tf.Height - sh) / 2f + ui.S(1), sw, sh);
            Color trackColor = !Enabled ? Theme.Border : isOn ? (hover ? Theme.AccentHover : Theme.Accent) : (hover ? Theme.TextDisabled : Theme.BorderStrong);
            using (GraphicsPath tp = Logo.RoundedRect(track, sh / 2f))
            using (SolidBrush b = new SolidBrush(trackColor))
                g.FillPath(b, tp);
            float knob = sh - ui.S(6);
            float kx = isOn ? track.Right - knob - ui.S(3) : track.Left + ui.S(3);
            using (SolidBrush b = new SolidBrush(Color.White))
                g.FillEllipse(b, kx, track.Top + ui.S(3), knob, knob);
            if (Focused && ShowFocusCues)
            {
                using (GraphicsPath fp = Logo.RoundedRect(RectangleF.Inflate(track, ui.S(3), ui.S(3)), sh / 2f + ui.S(3)))
                using (Pen p = new Pen(Theme.Accent, Math.Max(1f, ui.Factor)))
                    g.DrawPath(p, fp);
            }
        }
    }

    class ProgressLine : PaintedControl
    {
        double value;
        public bool Indeterminate { get; set; }
        public Color BarColor { get; set; }

        public ProgressLine(Ui ui) : base(ui)
        {
            BackColor = Color.Transparent;
            BarColor = Theme.Accent;
        }

        public double Value
        {
            get { return value; }
            set { this.value = Math.Max(0, Math.Min(1, value)); Invalidate(); }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            RectangleF r = new RectangleF(0, 0, Width - 1, Height - 1);
            float radius = r.Height / 2f;
            using (GraphicsPath track = Logo.RoundedRect(r, radius))
            using (SolidBrush b = new SolidBrush(Theme.Border))
                g.FillPath(b, track);
            RectangleF fill;
            if (Indeterminate)
            {
                double t = (DateTime.Now.Ticks / TimeSpan.TicksPerMillisecond % 1600) / 1600.0;
                float w = r.Width * 0.3f;
                float x = (float)((r.Width + w) * t) - w;
                fill = RectangleF.Intersect(new RectangleF(x, 0, w, r.Height), r);
            }
            else
            {
                fill = new RectangleF(0, 0, Math.Max(r.Height, (float)(r.Width * value)), r.Height);
            }
            if (fill.Width <= 0) return;
            using (GraphicsPath bar = Logo.RoundedRect(fill, radius))
            using (SolidBrush b = new SolidBrush(BarColor))
                g.FillPath(b, bar);
        }
    }

    /// <summary>1px horizontal rule.</summary>
    class Rule : Control
    {
        public Rule(Color color)
        {
            BackColor = color;
        }
    }

    /// <summary>A bordered single-line text input sized for the theme.</summary>
    class InputBox : Card
    {
        public readonly TextBox Box;
        readonly Ui ui;
        bool invalid;

        public InputBox(Ui ui, string text) : base(ui, Theme.Surface, Theme.BorderStrong)
        {
            this.ui = ui;
            Radius = 7;
            Box = new TextBox();
            Box.BorderStyle = BorderStyle.None;
            Box.Font = ui.Font(10f);
            Box.ForeColor = Theme.Text;
            Box.BackColor = Theme.Surface;
            Box.Text = text;
            Controls.Add(Box);
            Box.GotFocus += delegate { UpdateBorder(); };
            Box.LostFocus += delegate { UpdateBorder(); };
            Click += delegate { Box.Focus(); };
        }

        public bool Invalid
        {
            get { return invalid; }
            set { invalid = value; UpdateBorder(); }
        }

        void UpdateBorder()
        {
            BorderColor = invalid ? Theme.Danger : Box.Focused ? Theme.Accent : Theme.BorderStrong;
            Invalidate();
        }

        protected override void OnLayout(LayoutEventArgs levent)
        {
            base.OnLayout(levent);
            int padX = ui.S(10);
            int h = Box.PreferredHeight;
            Box.Bounds = new Rectangle(padX, (Height - h) / 2, Width - padX * 2, h);
        }
    }

    static class Shell
    {
        /// <summary>Opens a URL or folder through explorer.exe so browsers never start elevated.</summary>
        public static void OpenUrl(string url)
        {
            if (Program.SelfTestMode) return;
            try
            {
                System.Diagnostics.ProcessStartInfo psi = new System.Diagnostics.ProcessStartInfo(
                    System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"),
                    "\"" + url + "\"");
                psi.UseShellExecute = false;
                System.Diagnostics.Process.Start(psi);
            }
            catch (Exception ex)
            {
                ErrorDialog.Show(null, "Couldn't open the link", "Windows could not open " + url + ". You can copy it into your browser.", ex.ToString());
            }
        }
    }
}
