' BorsaWidget - tek tikla ac / kapa
Option Explicit

Dim fso, sh, svc, procs, p, found, scriptPath

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
scriptPath = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName)) & "\stock_widget.py"

If Not fso.FileExists(scriptPath) Then
    MsgBox "stock_widget.py bulunamadi:" & vbCrLf & scriptPath, 16, "BorsaWidget"
    WScript.Quit 1
End If

found = False
Set svc = GetObject("winmgmts:\\.\root\cimv2")
Set procs = svc.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='pythonw.exe' OR Name='python.exe'")
For Each p In procs
    If Not IsNull(p.CommandLine) Then
        If InStr(LCase(p.CommandLine), "stock_widget.py") > 0 Then
            found = True
            ' /F ile kapatiliyor: uygulamanin WM_CLOSE isleyicisi pencereyi
            ' "gizle" yapar (islemi sonlandirmaz), bu yuzden tam kapatma icin
            ' kuvvetli sonlandirma gerekir. Konum zaten surukleme birakilinca kaydedilir.
            sh.Run "taskkill /PID " & p.ProcessId & " /F", 0, True
        End If
    End If
Next

If Not found Then
    sh.Run "pythonw.exe " & Chr(34) & scriptPath & Chr(34), 0, False
End If
