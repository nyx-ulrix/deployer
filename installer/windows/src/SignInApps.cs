// Settings → Sign-in apps: the Google/GitHub OAuth apps people sign in to Deployer with.
// Reads "deployer oauth status -Json"; saves with "deployer oauth set <provider>", passing the
// Client ID and secret as child-process environment variables only (never argv, never logged).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

namespace DeployerSetup
{
    class SignInAppsDialog : ThemedForm
    {
        readonly string script;
        readonly string installDir;
        internal string provider = "google";
        IDictionary<string, object> status;
        string loadError;
        internal string message = "";
        internal bool messageIsError;
        bool busy;
        readonly Dictionary<string, string> ids = new Dictionary<string, string> { { "google", "" }, { "github", "" } };
        readonly Dictionary<string, string> secrets = new Dictionary<string, string> { { "google", "" }, { "github", "" } };

        /// <param name="script">deployer.ps1, or null for the self-test (no processes are started).</param>
        public SignInAppsDialog(string script, string installDir, float forcedScale) : base(forcedScale)
        {
            this.script = script;
            this.installDir = installDir;
            Text = "Sign-in apps";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ShowInTaskbar = false;
            BuildUi();
            if (script != null) Shown += delegate { LoadStatus(); };
        }

        string ProviderName { get { return provider == "google" ? "Google" : "GitHub"; } }

        IDictionary<string, object> Current
        {
            get { object v; return status != null && status.TryGetValue(provider, out v) ? v as IDictionary<string, object> : null; }
        }

        protected override void BuildUi()
        {
            int w = ui.S(560);
            int pad = ui.S(28);
            int cw = w - pad * 2;
            int y = ui.S(26);
            y += Add(new TextBlock(ui, "Sign-in apps (Google & GitHub)", ui.SemiBold(16f), Theme.Text), pad, y, cw) + ui.S(14);

            // Provider switch
            int bh = ui.S(34);
            int x = pad;
            foreach (string p in new[] { "google", "github" })
            {
                string captured = p;
                FlatButton tab = new FlatButton(ui, p == "google" ? "Google" : "GitHub", p == provider ? ButtonStyle.Primary : ButtonStyle.Secondary);
                int tw = tab.PreferredWidth(ui.S(100));
                tab.Bounds = new Rectangle(x, y, tw, bh);
                tab.Click += delegate { if (!busy && provider != captured) { provider = captured; message = ""; Rebuild(); } };
                Controls.Add(tab);
                x += tw + ui.S(8);
            }
            y += bh + ui.S(14);

            // Status
            IDictionary<string, object> cur = Current;
            string state;
            Color color;
            if (loadError != null) { state = loadError; color = Theme.DangerText; }
            else if (cur == null) { state = script == null ? "Not configured yet" : "Checking…"; color = Theme.TextMuted; }
            else if (Json.Bool(cur, "configured")) { state = "Configured · Client ID " + Json.Str(cur, "client_id"); color = Theme.SuccessText; }
            else if (Json.Str(cur, "client_id").Length > 0) { state = "Client secret missing: sign-in with " + ProviderName + " is off"; color = Theme.WarnText; }
            else { state = "Not configured yet: sign-in with " + ProviderName + " is off"; color = Theme.TextMuted; }
            y += Add(new TextBlock(ui, state, ui.SemiBold(10f), color), pad, y, cw) + ui.S(12);

            // Instructions
            string steps = provider == "google"
                ? "1. Open the Google Cloud console → APIs & Services → Credentials → Create credentials → OAuth client ID.\n" +
                  "2. Choose the type Web application. Under Authorized redirect URIs, add the callback URL below.\n" +
                  "3. Copy the Client ID and the Client secret into the boxes below (one value per box) and click Save."
                : "1. Open GitHub → Settings → Developer settings → OAuth Apps → New OAuth App.\n" +
                  "2. Set Authorization callback URL to the callback URL below, then register the app.\n" +
                  "3. Click Generate a new client secret. Copy the Client ID and the secret into the boxes below and click Save.";
            y += Add(new TextBlock(ui, steps, ui.Font(9.5f), Theme.Text), pad, y, cw) + ui.S(6);
            LinkText link = new LinkText(ui, provider == "google" ? "Open Google Cloud console → Credentials" : "Open GitHub developer settings",
                provider == "google" ? "https://console.cloud.google.com/apis/credentials" : "https://github.com/settings/developers");
            Size ls = link.Preferred();
            link.Bounds = new Rectangle(pad, y, Math.Min(ls.Width, cw), ls.Height);
            Controls.Add(link);
            y += ls.Height + ui.S(14);

            // Callback URL (read-only) + Copy
            int inputH = ui.S(36);
            y += Add(new TextBlock(ui, "Callback URL to register", ui.SemiBold(10f), Theme.Text), pad, y, cw) + ui.S(6);
            string callback = cur != null ? Json.Str(cur, "callback_url") : "";
            InputBox url = new InputBox(ui, callback.Length > 0 ? callback : (script == null ? "http://localhost:8080/v1/auth/oauth/" + provider + "/callback" : "…"));
            url.Box.ReadOnly = true;
            FlatButton copy = new FlatButton(ui, "Copy", ButtonStyle.Secondary);
            int cwid = copy.PreferredWidth(ui.S(80));
            url.Bounds = new Rectangle(pad, y, cw - cwid - ui.S(8), inputH);
            copy.Bounds = new Rectangle(pad + cw - cwid, y, cwid, inputH);
            copy.Enabled = callback.Length > 0;
            copy.Click += delegate
            {
                try { Clipboard.SetText(url.Box.Text); copy.Text = "Copied"; } catch (Exception) { }
            };
            Controls.Add(url);
            Controls.Add(copy);
            y += inputH + ui.S(14);

            // Client ID / secret
            y += Add(new TextBlock(ui, "Client ID", ui.SemiBold(10f), Theme.Text), pad, y, cw) + ui.S(6);
            InputBox idInput = new InputBox(ui, ids[provider]);
            idInput.Box.MaxLength = 500;
            idInput.Bounds = new Rectangle(pad, y, cw, inputH);
            idInput.Box.TextChanged += delegate { ids[provider] = idInput.Box.Text; };
            Controls.Add(idInput);
            y += inputH + ui.S(12);
            bool hasSecret = cur != null && Json.Bool(cur, "has_secret");
            TextBlock secretLabel = new TextBlock(ui, "Client secret", ui.SemiBold(10f), Theme.Text);
            secretLabel.SingleLine = true;
            int slw = Ui.MeasureWidth(secretLabel.Text, secretLabel.TextFont) + ui.S(12);
            Add(secretLabel, pad, y, slw);
            TextBlock secretHint = new TextBlock(ui, hasSecret ? "A secret is saved. Leave empty to keep it." : "Shown once by " + ProviderName + " when you create it.",
                ui.Font(9.5f), Theme.TextMuted);
            secretHint.SingleLine = true;
            secretHint.RightAlign = true;
            int drop = secretLabel.TextFont.Height - secretHint.TextFont.Height;
            y += Add(secretHint, pad + slw, y + drop, cw - slw) + drop + ui.S(6);
            InputBox secretInput = new InputBox(ui, secrets[provider]);
            secretInput.Box.UseSystemPasswordChar = true;
            secretInput.Box.MaxLength = 500;
            secretInput.Bounds = new Rectangle(pad, y, cw, inputH);
            secretInput.Box.TextChanged += delegate { secrets[provider] = secretInput.Box.Text; };
            Controls.Add(secretInput);
            y += inputH + ui.S(12);

            if (message.Length > 0)
                y += Add(new TextBlock(ui, message, ui.SemiBold(10f), messageIsError ? Theme.DangerText : Theme.SuccessText), pad, y, cw) + ui.S(10);
            y += ui.S(8);

            // Footer: Remove | Close, Save
            Panel footer = new Panel();
            footer.BackColor = Theme.SurfaceAlt;
            int fh = ui.S(68);
            footer.Bounds = new Rectangle(0, y, w, fh);
            Rule fr = new Rule(Theme.Border);
            fr.Bounds = new Rectangle(0, 0, w, Math.Max(1, ui.S(1)));
            footer.Controls.Add(fr);
            bh = ui.S(38);
            FlatButton save = new FlatButton(ui, busy ? "Saving…" : "Save", ButtonStyle.Primary);
            int sw = save.PreferredWidth(ui.S(96));
            save.Bounds = new Rectangle(w - pad - sw, (fh - bh) / 2, sw, bh);
            save.Enabled = !busy && loadError == null;
            save.Click += delegate { Save(); };
            footer.Controls.Add(save);
            FlatButton close = new FlatButton(ui, "Close", ButtonStyle.Secondary);
            int clw = close.PreferredWidth(ui.S(96));
            close.Bounds = new Rectangle(w - pad - sw - ui.S(10) - clw, (fh - bh) / 2, clw, bh);
            close.Click += delegate { Close(); };
            footer.Controls.Add(close);
            FlatButton remove = new FlatButton(ui, "Remove", ButtonStyle.DangerGhost);
            int rw = remove.PreferredWidth(ui.S(90));
            remove.Bounds = new Rectangle(pad - ui.S(10), (fh - bh) / 2, rw, bh);
            remove.Enabled = !busy && cur != null && (Json.Str(cur, "client_id").Length > 0 || hasSecret);
            remove.Click += delegate { Remove(); };
            footer.Controls.Add(remove);
            Controls.Add(footer);
            AcceptButton = save;
            CancelButton = close;
            ClientSize = new Size(w, y + fh);
        }

        int Add(TextBlock block, int x, int y, int width)
        {
            int h = block.LayoutAt(x, y, width);
            Controls.Add(block);
            return h;
        }

        /// <summary>The obvious paste mistakes, checked again (with the full rules) by the API.</summary>
        internal static string CheckValue(string provider, bool secret, string value)
        {
            string name = (provider == "google" ? "Google" : "GitHub") + (secret ? " Client secret" : " Client ID");
            if (value.Any(char.IsWhiteSpace) || Regex.IsMatch(value, @"^(client[ _-]?)?(id|secret)[\s:=]", RegexOptions.IgnoreCase))
                return "Paste only the " + name + " - not the whole block (the value has spaces or an ID/SECRET label in it).";
            bool googleId = Regex.IsMatch(value, @"^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$");
            if (secret && googleId) return "That looks like the Client ID, not the Client secret.";
            if (!secret && provider == "google" && !googleId)
                return "That is not a Google Client ID - it looks like 1234-abc.apps.googleusercontent.com.";
            return null;
        }

        void SetMessage(string text, bool isError)
        {
            message = text;
            messageIsError = isError;
            Rebuild();
        }

        void Save()
        {
            string id = ids[provider].Trim();
            string secret = secrets[provider].Trim();
            IDictionary<string, object> cur = Current;
            string error = id.Length == 0 ? "Enter the Client ID." : CheckValue(provider, false, id);
            if (error == null && secret.Length > 0) error = CheckValue(provider, true, secret);
            if (error == null && secret.Length == 0 && !(cur != null && Json.Bool(cur, "has_secret"))) error = "Enter the Client secret.";
            if (error != null) { SetMessage(error, true); return; }
            Dictionary<string, string> env = new Dictionary<string, string>
            {
                { "DEPLOYER_OAUTH_CLIENT_ID", id },
                { "DEPLOYER_OAUTH_CLIENT_SECRET", secret }
            };
            Run(new[] { "oauth", "set", provider }, env, "Saved. People can now sign in with " + ProviderName + ".");
        }

        void Remove()
        {
            DialogResult r = MessageDialog.Ask(this, "Remove the " + ProviderName + " sign-in app?",
                "Nobody can sign in with " + ProviderName + " until you add it again. Accounts and their other sign-in methods are kept.",
                IconKind.Warn, Theme.Danger, "Remove", ButtonStyle.Danger, "Cancel");
            if (r == DialogResult.Yes) Run(new[] { "oauth", "clear", provider }, null, ProviderName + " sign-in app removed.");
        }

        void Run(string[] command, IDictionary<string, string> env, string doneText)
        {
            if (script == null || busy) return;
            busy = true;
            message = "";
            Rebuild();
            string target = provider;
            List<string> args = new List<string>(command) { "-InstallDir", installDir };
            List<string> lines = new List<string>();
            ScriptRunner runner = new ScriptRunner();
            runner.OutputLine += line => { lock (lines) lines.Add(line); };
            runner.Exited += code => Post(() =>
            {
                busy = false;
                if (code == 0)
                {
                    secrets[target] = "";
                    ids[target] = "";
                    message = doneText;
                    messageIsError = false;
                    LoadStatus();
                }
                else
                {
                    string error;
                    lock (lines) error = lines.Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("[x] "));
                    message = error != null ? error.Substring(4) : "Deployer reported a problem (exit code " + code + ").";
                    messageIsError = true;
                }
                Rebuild();
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

        void LoadStatus()
        {
            string args = ProcessUtil.JoinArgs(ScriptRunner.ScriptArgs(script, new[] { "oauth", "status", "-Json", "-InstallDir", installDir }));
            ThreadPool.QueueUserWorkItem(delegate
            {
                ProcessResult r = ProcessUtil.Run(AppInfo.PowerShellExe, args, 120000);
                IDictionary<string, object> d = null;
                int a = r.StdOut.IndexOf('{'), b = r.StdOut.LastIndexOf('}');
                if (r.ExitCode == 0 && a >= 0 && b > a)
                {
                    try { d = Json.Parse(r.StdOut.Substring(a, b - a + 1)) as IDictionary<string, object>; } catch (Exception) { }
                }
                Post(() => ApplyStatus(d, d == null ? "Couldn't read the sign-in settings. Make sure Deployer is running, then open this again." : null));
            });
        }

        internal void ApplyStatus(IDictionary<string, object> d, string error)
        {
            status = d;
            loadError = error;
            if (d != null)
            {
                foreach (string p in new[] { "google", "github" })
                {
                    object v;
                    IDictionary<string, object> pd = d.TryGetValue(p, out v) ? v as IDictionary<string, object> : null;
                    if (pd != null && ids[p].Length == 0) ids[p] = Json.Str(pd, "client_id");
                }
            }
            Rebuild();
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
