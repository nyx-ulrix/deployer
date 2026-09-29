// Settings → Reset a password: forgotten-password recovery for Deployer accounts (A-003).
// Runs "deployer reset-password [email]"; the new password is passed as a child-process
// environment variable only (never argv, never logged). Being on this PC is the proof of ownership.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;

namespace DeployerSetup
{
    class ResetPasswordDialog : ThemedForm
    {
        const int MinLength = 10;
        readonly string script;
        readonly string installDir;
        string email = "", password = "", confirm = "";
        internal string message = "";
        internal bool messageIsError;
        bool busy;

        /// <param name="script">deployer.ps1, or null for the self-test (no processes are started).</param>
        public ResetPasswordDialog(string script, string installDir, float forcedScale) : base(forcedScale)
        {
            this.script = script;
            this.installDir = installDir;
            Text = "Reset a password";
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
            y += Add(new TextBlock(ui, "Reset a password", ui.SemiBold(16f), Theme.Text), pad, y, cw) + ui.S(6);
            y += Add(new TextBlock(ui, "Forgot the password for your Deployer account? Set a new one here. " +
                "The account is signed out on every device; sign in again with the new password.",
                ui.Font(10f), Theme.TextMuted), pad, y, cw) + ui.S(18);

            int inputH = ui.S(36);
            y = Field(y, pad, cw, inputH, "Account email (leave empty for the owner)", email, false, v => email = v);
            y = Field(y, pad, cw, inputH, "New password (at least " + MinLength + " characters)", password, true, v => password = v);
            y = Field(y, pad, cw, inputH, "Type it again", confirm, true, v => confirm = v);

            if (message.Length > 0)
                y += Add(new TextBlock(ui, message, ui.SemiBold(10f), messageIsError ? Theme.DangerText : Theme.SuccessText), pad, y, cw) + ui.S(10);
            y += ui.S(8);

            Panel footer = new Panel();
            footer.BackColor = Theme.SurfaceAlt;
            int fh = ui.S(68);
            footer.Bounds = new Rectangle(0, y, w, fh);
            Rule fr = new Rule(Theme.Border);
            fr.Bounds = new Rectangle(0, 0, w, Math.Max(1, ui.S(1)));
            footer.Controls.Add(fr);
            int bh = ui.S(38);
            FlatButton reset = new FlatButton(ui, busy ? "Resetting…" : "Reset password", ButtonStyle.Primary);
            int rw = reset.PreferredWidth(ui.S(96));
            reset.Bounds = new Rectangle(w - pad - rw, (fh - bh) / 2, rw, bh);
            reset.Enabled = !busy;
            reset.Click += delegate { Reset(); };
            footer.Controls.Add(reset);
            FlatButton close = new FlatButton(ui, "Close", ButtonStyle.Secondary);
            int clw = close.PreferredWidth(ui.S(96));
            close.Bounds = new Rectangle(w - pad - rw - ui.S(10) - clw, (fh - bh) / 2, clw, bh);
            close.Click += delegate { Close(); };
            footer.Controls.Add(close);
            Controls.Add(footer);
            AcceptButton = reset;
            CancelButton = close;
            ClientSize = new Size(w, y + fh);
        }

        int Field(int y, int pad, int cw, int inputH, string label, string value, bool secret, Action<string> set)
        {
            y += Add(new TextBlock(ui, label, ui.SemiBold(10f), Theme.Text), pad, y, cw) + ui.S(6);
            InputBox input = new InputBox(ui, value);
            input.Box.MaxLength = secret ? 1024 : 255;
            input.Box.UseSystemPasswordChar = secret;
            input.Bounds = new Rectangle(pad, y, cw, inputH);
            input.Box.TextChanged += delegate { set(input.Box.Text); };
            Controls.Add(input);
            return y + inputH + ui.S(12);
        }

        int Add(TextBlock block, int x, int y, int width)
        {
            int h = block.LayoutAt(x, y, width);
            Controls.Add(block);
            return h;
        }

        /// <summary>The checks the form can make; the API checks the password again.</summary>
        internal static string Check(string password, string confirm)
        {
            if (password.Length < MinLength) return "The new password must be at least " + MinLength + " characters.";
            if (password != confirm) return "The two passwords are different.";
            return null;
        }

        void SetMessage(string text, bool isError)
        {
            message = text;
            messageIsError = isError;
            Rebuild();
        }

        void Reset()
        {
            if (busy) return;
            string error = Check(password, confirm);
            if (error != null) { SetMessage(error, true); return; }
            if (script == null) return;
            busy = true;
            message = "";
            Rebuild();
            List<string> args = new List<string> { "reset-password" };
            if (email.Trim().Length > 0) args.Add(email.Trim());
            args.AddRange(new[] { "-InstallDir", installDir });
            Dictionary<string, string> env = new Dictionary<string, string> { { "DEPLOYER_NEW_PASSWORD", password } };
            List<string> lines = new List<string>();
            ScriptRunner runner = new ScriptRunner();
            runner.OutputLine += line => { lock (lines) lines.Add(line); };
            runner.Exited += code => Post(() =>
            {
                busy = false;
                string prefix = code == 0 ? "[ok] " : "[x] ";
                string last;
                lock (lines) last = lines.Select(l => l.Trim()).LastOrDefault(l => l.StartsWith(prefix));
                if (last != null) last = last.Substring(prefix.Length);
                if (code == 0) password = confirm = "";
                SetMessage(last ?? (code == 0 ? "Password reset. Sign in with the new password."
                    : "Deployer reported a problem (exit code " + code + ")."), code != 0);
            });
            try
            {
                runner.Start(script, args, env);
            }
            catch (Exception ex)
            {
                busy = false;
                SetMessage("Couldn't start PowerShell: " + ex.Message, true);
            }
        }

        void Post(Action a)
        {
            try
            {
                if (!IsDisposed && IsHandleCreated) BeginInvoke(a);
            }
            catch (InvalidOperationException)
            {
            }
        }
    }
}
