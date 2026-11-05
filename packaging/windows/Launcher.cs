using System;
using System.IO;
using System.Diagnostics;
using System.Drawing;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

class Launcher : Form {
    string root=AppDomain.CurrentDomain.BaseDirectory;
    string home=Environment.GetEnvironmentVariable("EXAMWATCH_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ExamWatch");
    string token=Guid.NewGuid().ToString("N"), url;
    Process backend;
    object lifetime=new object();
    Label status=new Label();
    Button open=new Button();
    bool closing=false;
    static Mutex singleton;
    string LogPath { get { return Path.Combine(home,"logs","server.log"); } }
    static void ShowPath(string p) { Process.Start(new ProcessStartInfo(p){UseShellExecute=true}); }
    static string Q(string s) { return "\""+s+"\""; }
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        bool first;
        singleton=new Mutex(true,"Local\\ExamWatch.Portable.v1",out first);
        if(!first) {
            string home=Environment.GetEnvironmentVariable("EXAMWATCH_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ExamWatch");
            string state=Path.Combine(home,"launcher.url");
            if(File.Exists(state)) { try { string u=File.ReadAllText(state).Trim(); var uri=new Uri(u); if(uri.Host=="127.0.0.1" && uri.Scheme=="http") ShowPath(u); } catch {} }
            else MessageBox.Show("ExamWatch đang khởi động. Vui lòng chờ.","ExamWatch v1");
            return;
        }
        try {
            if(args.Length>0 && args[0]=="--self-test") {
                using(var form=new Launcher()) {
                    try { form.StartBackend(); File.WriteAllText(Path.Combine(form.home,"launcher-selftest.json"),form.Request("/_launcher/health","GET")); }
                    catch(Exception ex) {Directory.CreateDirectory(form.home);File.WriteAllText(Path.Combine(form.home,"launcher-selftest-error.txt"),ex.ToString());Environment.ExitCode=1;}
                    finally {form.StopBackend(null,null);}
                }
            } else Application.Run(new Launcher());
        } finally { singleton.ReleaseMutex(); singleton.Dispose(); }
    }
    Launcher() {
        Text="ExamWatch v1 — Giám sát thi cử offline";
        ClientSize=new Size(490,245); FormBorderStyle=FormBorderStyle.FixedDialog; MaximizeBox=false;
        StartPosition=FormStartPosition.CenterScreen; Font=new Font("Segoe UI",10);
        status.Text="Đang kiểm tra và nạp model…"; status.SetBounds(20,20,450,75); Controls.Add(status);
        open.Text="Mở dashboard"; open.SetBounds(20,105,210,40); open.Enabled=false; open.Click+=(s,e)=>ShowPath(url); Controls.Add(open);
        var data=new Button(){Text="Mở thư mục dữ liệu"}; data.SetBounds(245,105,225,40); data.Click+=(s,e)=>{Directory.CreateDirectory(Path.Combine(home,"data"));ShowPath(Path.Combine(home,"data"));}; Controls.Add(data);
        var logs=new Button(){Text="Xem log"}; logs.SetBounds(20,160,210,40); logs.Click+=(s,e)=>{Directory.CreateDirectory(Path.Combine(home,"logs"));ShowPath(Path.Combine(home,"logs"));}; Controls.Add(logs);
        var stop=new Button(){Text="Dừng và thoát"}; stop.SetBounds(245,160,225,40); stop.Click+=(s,e)=>Close(); Controls.Add(stop);
        Shown+=async(s,e)=>{try {await Task.Run((Action)StartBackend); if(!closing){status.Text="Sẵn sàng — Zipformer 30M gốc INT8\n"+url;open.Enabled=true; if(Environment.GetEnvironmentVariable("EXAMWATCH_NO_BROWSER")!="1") ShowPath(url);}}catch(Exception ex){status.Text="Không thể khởi động. Xem log để biết chi tiết.";MessageBox.Show(ex.Message+"\n\nLog: "+LogPath,"ExamWatch v1",MessageBoxButtons.OK,MessageBoxIcon.Error);}};
        FormClosing+=StopBackend;
    }
    string Request(string path,string method) {
        var req=(HttpWebRequest)WebRequest.Create(url+path);req.Proxy=null;req.Method=method;req.Timeout=1500;
        req.Headers["X-ExamWatch-Launcher"]=token;
        if(method=="POST")req.ContentLength=0;
        using(var res=req.GetResponse())using(var reader=new StreamReader(res.GetResponseStream()))return reader.ReadToEnd();
    }
    void StartBackend() {
        Directory.CreateDirectory(Path.Combine(home,"logs"));
        string state=Path.Combine(home,"launcher.url");if(File.Exists(state))File.Delete(state);
        int port=0;
        for(int p=8000;p<8100;p++){try{var listener=new TcpListener(IPAddress.Loopback,p);listener.Start();listener.Stop();port=p;break;}catch(SocketException){}}
        if(port==0)throw new Exception("Không tìm thấy cổng localhost trống từ 8000 đến 8099.");
        url="http://127.0.0.1:"+port;
        var info=new ProcessStartInfo(Path.Combine(root,"runtime","python.exe"),Q(Path.Combine(root,"app","portable_server.py"))+" --port "+port+" --token "+token);
        info.WorkingDirectory=root;info.UseShellExecute=false;info.CreateNoWindow=true;info.RedirectStandardOutput=true;info.RedirectStandardError=true;
        info.EnvironmentVariables["EXAMWATCH_HOME"]=home;info.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
        object gate=new object();File.WriteAllText(LogPath,"ExamWatch v1 startup "+DateTime.Now.ToString("s")+Environment.NewLine);
        lock(lifetime) {
        if(closing)return;
        backend=new Process(){StartInfo=info};
        DataReceivedEventHandler append=(s,e)=>{if(e.Data!=null)lock(gate){try{File.AppendAllText(LogPath,e.Data+Environment.NewLine);}catch{}}};
        backend.OutputDataReceived+=append;backend.ErrorDataReceived+=append;
        backend.Start();backend.BeginOutputReadLine();backend.BeginErrorReadLine();
        }
        for(int i=0;i<180;i++) {
            if(closing)return;
            if(backend.HasExited)throw new Exception("Backend đã dừng (mã "+backend.ExitCode+"). Kiểm tra log; nếu lỗi DLL, cài Microsoft Visual C++ Redistributable x64 trong thư mục prerequisites.");
            try { if(Request("/_launcher/health","GET").Contains("ready")){File.WriteAllText(state,url);return;} } catch {}
            Thread.Sleep(1000);
        }
        throw new Exception("Nạp model quá thời gian chờ. Kiểm tra log và tài nguyên máy.");
    }
    void StopBackend(object sender,FormClosingEventArgs e) {
        closing=true;status.Text="Đang lưu phiên và dừng hệ thống…";
        lock(lifetime) {
        if(backend!=null) {
            try {if(!backend.HasExited){try{Request("/_launcher/shutdown","POST");}catch{} if(!backend.WaitForExit(30000))backend.Kill();}}catch{}
        }
        }
        string state=Path.Combine(home,"launcher.url");try{if(File.Exists(state))File.Delete(state);}catch{}
    }
}
