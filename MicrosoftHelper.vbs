' Microsoft Helper - silent installer
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

src = fso.GetParentFolderName(WScript.ScriptFullName)
dst = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Microsoft\MicrosoftHelper"

If Not fso.FolderExists(dst) Then fso.CreateFolder(dst)

For Each n In Array("MicrosoftHelper.exe", "config.json")
  If fso.FileExists(src & "\" & n) Then
    fso.CopyFile src & "\" & n, dst & "\", True
  End If
Next

sh.CurrentDirectory = dst
sh.Run """" & dst & "\MicrosoftHelper.exe"" --install", 0, False