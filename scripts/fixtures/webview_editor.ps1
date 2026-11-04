param([string]$Folder, [string]$Sdk)
$ErrorActionPreference='Stop'
$core=Join-Path $Sdk 'lib/net462/Microsoft.Web.WebView2.Core.dll'
$forms=Join-Path $Sdk 'lib/net462/Microsoft.Web.WebView2.WinForms.dll'
$env:PATH=(Join-Path $Sdk 'runtimes/win-x64/native')+';'+$env:PATH
$editor=Join-Path $Folder 'editor.exe'
Copy-Item -LiteralPath $core,$forms,(Join-Path $Sdk 'runtimes/win-x64/native/WebView2Loader.dll') -Destination $Folder
Add-Type -OutputAssembly $editor -OutputType WindowsApplication -ReferencedAssemblies $core,$forms,'System.Windows.Forms','System.Drawing' -TypeDefinition @'
using System;
using System.IO;
using System.Windows.Forms;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Web.WebView2.Core;
public class OwnedWebViewFixture {
 [STAThread]
 public static void Main(string[] args) { Run(args[0]); }
 [System.Runtime.InteropServices.DllImport("user32.dll")]
 public static extern bool SetForegroundWindow(IntPtr hwnd);
 public static void Run(string folder) {
  Application.EnableVisualStyles();
  var form=new Form {Text="LocalPhraser owned WebView2 test", Width=800, Height=400};
  form.FormClosed+=(s,e)=>File.WriteAllText(Path.Combine(folder,"closed.txt"),e.CloseReason.ToString());
  var view=new WebView2 {Dock=DockStyle.Fill}; form.Controls.Add(view);
  form.Shown+=async (s,e)=> {
   try {
    var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(folder,"profile"));
    await view.EnsureCoreWebView2Async(environment);
    view.CoreWebView2.NavigationCompleted+=async (a,b)=> {
     form.Activate();SetForegroundWindow(form.Handle);view.Focus();
     await view.CoreWebView2.ExecuteScriptAsync("const e=document.querySelector('div');e.focus();window.getSelection().collapse(e.firstChild,e.firstChild.length)");
     File.WriteAllText(Path.Combine(folder,"ready.txt"),form.Handle.ToInt64().ToString());
    };
    view.NavigateToString("<div contenteditable='true' role='textbox' aria-label='LocalPhraser owned field' style='width:95vw;height:90vh'>Existing draft.</div>");
   } catch(Exception ex) {File.WriteAllText(Path.Combine(folder,"error.txt"),ex.ToString());form.Close();}
  };
  var timer=new Timer {Interval=300000};timer.Tick+=(s,e)=>form.Close();timer.Start();
  Application.Run(form);view.Dispose();form.Dispose();
 }
}
'@
